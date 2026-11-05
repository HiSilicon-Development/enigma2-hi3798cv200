#ifndef E2_HISTB_DRM_H
#define E2_HISTB_DRM_H

#include <algorithm>
#include <cerrno>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <fcntl.h>
#include <mutex>
#include <unistd.h>
#include <sys/ioctl.h>
#include <linux/fb.h>
#include <xf86drm.h>
#include <xf86drmMode.h>
#include <drm_fourcc.h>
#include <lib/base/eerror.h>

/* One DRM file/master per process, shared by AVControl, the UI and decoder.
 * dup() preserves DRM-file identity; separately open()ing card0 does not.
 * All KMS commits hold mutex through completion, including page-flip events. */
struct HistbDrmSession
{
	std::mutex mutex;
	int fd = -1;
	uint32_t connector = 0, crtc = 0, primary = 0;
	/* fbdev allocation/stride remain physical; sourceW/H are skin pixels. */
	uint32_t sourceW = 0, sourceH = 0;
	uint32_t framebufferW = 0, framebufferH = 0, sourcePitch = 0;
	uint32_t osdFb = 0;
	double refreshPeriodUs = 0.0;
};

inline double histbDrmModePeriodUs(const drmModeModeInfo &mode)
{
	if (!mode.clock || !mode.htotal || !mode.vtotal) return 0.0;
	double period = 1000.0 * mode.htotal * mode.vtotal / mode.clock;
	if (mode.flags & DRM_MODE_FLAG_INTERLACE) period /= 2;
	if (mode.flags & DRM_MODE_FLAG_DBLSCAN) period *= 2;
	if (mode.vscan > 1) period *= mode.vscan;
	return period;
}


/* External inline linkage is intentional: the function-local session must be
 * shared across decoder.cpp, avcontrol.cpp and fb.cpp, not one per TU. */
inline HistbDrmSession &histbDrmSession()
{
	static HistbDrmSession session;
	return session;
}

inline uint32_t histbDrmProperty(int fd, uint32_t object, uint32_t type,
	const char *name, uint64_t *value = nullptr)
{
	uint32_t id = 0;
	drmModeObjectPropertiesPtr props = drmModeObjectGetProperties(fd, object, type);
	if (!props)
		return 0;
	for (uint32_t i = 0; i < props->count_props; ++i)
	{
		drmModePropertyPtr p = drmModeGetProperty(fd, props->props[i]);
		if (p && !strcmp(p->name, name))
		{
			id = p->prop_id;
			if (value) *value = props->prop_values[i];
		}
		if (p) drmModeFreeProperty(p);
		if (id) break;
	}
	drmModeFreeObjectProperties(props);
	return id;
}

/* Caller holds session.mutex. The fd stays alive until process exit so mode
 * ownership is not lost on channel change or while the decoder is stopped. */
inline int histbDrmOpen()
{
	auto &s = histbDrmSession();
	if (s.fd >= 0) return s.fd;
	for (int card = 0; card < 8; ++card)
	{
		char path[32];
		snprintf(path, sizeof(path), "/dev/dri/card%d", card);
		int fd = open(path, O_RDWR | O_CLOEXEC);
		if (fd < 0) continue;
		drmModeResPtr res = drmModeGetResources(fd);
		if (!res) { close(fd); continue; }
		for (int i = 0; i < res->count_connectors; ++i)
		{
			drmModeConnectorPtr c = drmModeGetConnector(fd, res->connectors[i]);
			if (!c) continue;
			bool hdmi = c->connector_type == DRM_MODE_CONNECTOR_HDMIA || c->connector_type == DRM_MODE_CONNECTOR_HDMIB;
			if (hdmi && c->connection == DRM_MODE_CONNECTED && c->count_modes && res->count_crtcs)
			{
				uint32_t crtc = 0;
				drmModeEncoderPtr enc = c->encoder_id ? drmModeGetEncoder(fd, c->encoder_id) : nullptr;
				if (enc) { crtc = enc->crtc_id; drmModeFreeEncoder(enc); }
				/* CV200 has one display pipeline. */
				if (!crtc && res->count_crtcs == 1) crtc = res->crtcs[0];
				if (crtc && drmSetClientCap(fd, DRM_CLIENT_CAP_UNIVERSAL_PLANES, 1) == 0 &&
					drmSetClientCap(fd, DRM_CLIENT_CAP_ATOMIC, 1) == 0 &&
					(drmIsMaster(fd) || drmSetMaster(fd) == 0))
				{
					s.fd = fd; s.connector = c->connector_id; s.crtc = crtc;
					drmModeFreeConnector(c); drmModeFreeResources(res);
					return fd;
				}
			}
			drmModeFreeConnector(c);
		}
		drmModeFreeResources(res);
		close(fd);
	}
	return -1;
}


inline bool histbDrmAdd(drmModeAtomicReqPtr req, uint32_t obj, uint32_t type,
	const char *name, uint64_t value)
{
	auto &s = histbDrmSession();
	uint32_t id = histbDrmProperty(s.fd, obj, type, name);
	return id && drmModeAtomicAddProperty(req, obj, id, value) >= 0;
}

inline bool histbDrmSameMode(const drmModeModeInfo &a, const drmModeModeInfo &b)
{
	return a.clock == b.clock && a.hdisplay == b.hdisplay &&
		a.hsync_start == b.hsync_start && a.hsync_end == b.hsync_end && a.htotal == b.htotal &&
		a.vdisplay == b.vdisplay && a.vsync_start == b.vsync_start &&
		a.vsync_end == b.vsync_end && a.vtotal == b.vtotal && a.flags == b.flags && a.vscan == b.vscan;
}

/* Caller holds mutex. GP0 scales the skin canvas directly from fbdev's GEM.
 * Never disable another graphics input to evade the shared-group constraint,
 * or copy video/OSD pixels to conceal a rejected hardware configuration. */
inline bool histbDrmSetMode(const drmModeModeInfo &mode)
{
	auto &s = histbDrmSession();
	if (histbDrmOpen() < 0) return false;
	if (!s.framebufferW)
	{
		int fb = open("/dev/fb0", O_RDWR | O_CLOEXEC);
		fb_var_screeninfo v = {}; fb_fix_screeninfo f = {};
		if (fb < 0) return false;
		bool valid = ioctl(fb, FBIOGET_VSCREENINFO, &v) == 0 && ioctl(fb, FBIOGET_FSCREENINFO, &f) == 0 &&
			v.bits_per_pixel == 32 && v.xoffset == 0 && v.yoffset == 0 &&
			f.line_length >= v.xres * 4 && uint64_t(f.line_length) * v.yres <= f.smem_len;
		close(fb);
		if (!valid) return false;
		s.framebufferW = v.xres; s.framebufferH = v.yres; s.sourcePitch = f.line_length;
		if (!s.sourceW) { s.sourceW = v.xres; s.sourceH = v.yres; }
	}
	if (!s.sourceW || !s.sourceH || s.sourceW > s.framebufferW || s.sourceH > s.framebufferH)
		return false;
	drmModeCrtcPtr before = drmModeGetCrtc(s.fd, s.crtc);
	drmModePlaneResPtr planes = drmModeGetPlaneResources(s.fd);
	if (!before || !before->mode_valid || !planes)
	{
		if (before) drmModeFreeCrtc(before);
		if (planes) drmModeFreePlaneResources(planes);
		return false;
	}
	uint32_t primary = 0, currentFb = 0;
	for (uint32_t i = 0; i < planes->count_planes; ++i)
	{
		drmModePlanePtr p = drmModeGetPlane(s.fd, planes->planes[i]);
		uint64_t type = 0;
		if (p && p->crtc_id == s.crtc && p->fb_id &&
			histbDrmProperty(s.fd, p->plane_id, DRM_MODE_OBJECT_PLANE, "type", &type) && type == DRM_PLANE_TYPE_PRIMARY)
		{ primary = p->plane_id; currentFb = p->fb_id; }
		if (p) drmModeFreePlane(p);
	}
	uint32_t fb = s.osdFb;
	if (primary && !fb)
	{
		drmModeFBPtr old = drmModeGetFB(s.fd, currentFb);
		if (old && old->handle)
		{
			uint32_t handles[4] = {old->handle, 0, 0, 0}, pitches[4] = {old->pitch, 0, 0, 0}, offsets[4] = {};
			if (old->width == s.framebufferW && old->height >= s.framebufferH && old->pitch == s.sourcePitch)
				drmModeAddFB2(s.fd, s.framebufferW, s.framebufferH, DRM_FORMAT_ARGB8888, handles, pitches, offsets, &fb, 0);
			drmCloseBufferHandle(s.fd, old->handle);
		}
		if (old) drmModeFreeFB(old);
	}
	uint32_t blob = 0, previousBlob = 0;
	drmModeAtomicReqPtr req = drmModeAtomicAlloc(), rollback = drmModeAtomicAlloc();
	bool ok = primary && fb && req && rollback &&
		drmModeCreatePropertyBlob(s.fd, &mode, sizeof(mode), &blob) == 0 &&
		drmModeCreatePropertyBlob(s.fd, &before->mode, sizeof(before->mode), &previousBlob) == 0;
	auto add = [&](uint32_t obj, uint32_t type, const char *name, uint64_t value) {
		uint64_t old = 0;
		uint32_t id = histbDrmProperty(s.fd, obj, type, name, &old);
		if (obj == s.crtc && !strcmp(name, "MODE_ID")) old = previousBlob;
		return id && drmModeAtomicAddProperty(rollback, obj, id, old) >= 0 &&
			drmModeAtomicAddProperty(req, obj, id, value) >= 0;
	};
	if (ok) ok = add(s.connector, DRM_MODE_OBJECT_CONNECTOR, "CRTC_ID", s.crtc) &&
		add(s.crtc, DRM_MODE_OBJECT_CRTC, "MODE_ID", blob) && add(s.crtc, DRM_MODE_OBJECT_CRTC, "ACTIVE", 1);
	for (uint32_t i = 0; i < planes->count_planes && ok; ++i)
	{
		drmModePlanePtr p = drmModeGetPlane(s.fd, planes->planes[i]);
		if (!p) { ok = false; break; }
		if (p->plane_id == primary)
		{
			ok = add(primary, DRM_MODE_OBJECT_PLANE, "FB_ID", fb) &&
				add(primary, DRM_MODE_OBJECT_PLANE, "CRTC_ID", s.crtc) &&
				add(primary, DRM_MODE_OBJECT_PLANE, "SRC_X", 0) && add(primary, DRM_MODE_OBJECT_PLANE, "SRC_Y", 0) &&
				add(primary, DRM_MODE_OBJECT_PLANE, "SRC_W", uint64_t(s.sourceW) << 16) &&
				add(primary, DRM_MODE_OBJECT_PLANE, "SRC_H", uint64_t(s.sourceH) << 16) &&
				add(primary, DRM_MODE_OBJECT_PLANE, "CRTC_X", 0) && add(primary, DRM_MODE_OBJECT_PLANE, "CRTC_Y", 0) &&
				add(primary, DRM_MODE_OBJECT_PLANE, "CRTC_W", mode.hdisplay) &&
				add(primary, DRM_MODE_OBJECT_PLANE, "CRTC_H", mode.vdisplay);
			if (histbDrmProperty(s.fd, primary, DRM_MODE_OBJECT_PLANE, "pixel blend mode"))
				ok = ok && add(primary, DRM_MODE_OBJECT_PLANE, "pixel blend mode", 1);
		}
		else if (p->crtc_id == s.crtc && p->fb_id)
		{
			bool graphics = false;
			for (uint32_t j = 0; j < p->count_formats; ++j)
				if (p->formats[j] == DRM_FORMAT_ARGB8888 || p->formats[j] == DRM_FORMAT_XRGB8888) graphics = true;
			/* Keep every source/crop/buffer unchanged. V1 has no scaler: the
			 * kernel must reject a destination resize it cannot implement. */
			if (!graphics)
			{
				const char *names[] = {"CRTC_X", "CRTC_Y", "CRTC_W", "CRTC_H"};
				for (int j = 0; j < 4 && ok; ++j)
				{
					uint64_t value = 0;
					ok = histbDrmProperty(s.fd, p->plane_id, DRM_MODE_OBJECT_PLANE, names[j], &value);
					int64_t scaled = int64_t(value) * (j % 2 ? mode.vdisplay : mode.hdisplay) /
						(j % 2 ? before->mode.vdisplay : before->mode.hdisplay);
					ok = ok && add(p->plane_id, DRM_MODE_OBJECT_PLANE, names[j], uint64_t(scaled));
				}
			}
		}
		drmModeFreePlane(p);
	}
	if (ok) ok = drmModeAtomicCommit(s.fd, req, DRM_MODE_ATOMIC_TEST_ONLY | DRM_MODE_ATOMIC_ALLOW_MODESET, nullptr) == 0;
	if (ok) ok = drmModeAtomicCommit(s.fd, req, DRM_MODE_ATOMIC_ALLOW_MODESET, nullptr) == 0;
	if (ok)
	{
		drmModeCrtcPtr actual = drmModeGetCrtc(s.fd, s.crtc);
		ok = actual && actual->mode_valid && histbDrmSameMode(mode, actual->mode);
		if (actual && actual->mode_valid) s.refreshPeriodUs = histbDrmModePeriodUs(actual->mode);
		if (actual) drmModeFreeCrtc(actual);
		const char *names[] = {"FB_ID", "SRC_X", "SRC_Y", "SRC_W", "SRC_H", "CRTC_X", "CRTC_Y", "CRTC_W", "CRTC_H"};
		uint64_t expected[] = {fb, 0, 0, uint64_t(s.sourceW) << 16, uint64_t(s.sourceH) << 16, 0, 0, mode.hdisplay, mode.vdisplay};
		for (unsigned int i = 0; i < sizeof(expected) / sizeof(expected[0]) && ok; ++i)
		{
			uint64_t value = 0;
			ok = histbDrmProperty(s.fd, primary, DRM_MODE_OBJECT_PLANE, names[i], &value) && value == expected[i];
		}
		if (!ok)
		{
			eWarning("[histb-drm] mode readback mismatch; restoring prior KMS state");
			if (drmModeAtomicCommit(s.fd, rollback, DRM_MODE_ATOMIC_ALLOW_MODESET, nullptr) != 0)
			{
				// Retain the alias if it might still be bound: RMFB would blank it.
				s.osdFb = fb;
				eWarning("[histb-drm] KMS rollback failed: %s", strerror(errno));
			}
			else s.refreshPeriodUs = histbDrmModePeriodUs(before->mode);
		}
	}
	if (ok)
	{
		s.osdFb = fb; s.primary = primary;
		s.refreshPeriodUs = histbDrmModePeriodUs(mode);
		eDebug("[histb-drm] GP0 %ux%u stride %u -> %ux%u@%u", s.sourceW, s.sourceH, s.sourcePitch, mode.hdisplay, mode.vdisplay, mode.vrefresh);
	}
	else eWarning("[histb-drm] rejected %s@%u, GP0 %ux%u: %s", mode.name, mode.vrefresh, s.sourceW, s.sourceH, strerror(errno));
	if (req) drmModeAtomicFree(req);
	if (rollback) drmModeAtomicFree(rollback);
	if (blob) drmModeDestroyPropertyBlob(s.fd, blob);
	if (previousBlob) drmModeDestroyPropertyBlob(s.fd, previousBlob);
	if (fb && fb != s.osdFb) drmModeRmFB(s.fd, fb);
	drmModeFreePlaneResources(planes);
	drmModeFreeCrtc(before);
	return ok;
}

inline bool histbOsdSetGeometry(uint32_t width, uint32_t height)
{
	auto &s = histbDrmSession();
	std::lock_guard<std::mutex> lock(s.mutex);
	if (histbDrmOpen() < 0) return false;
	drmModeCrtcPtr crtc = drmModeGetCrtc(s.fd, s.crtc);
	if (!crtc || !crtc->mode_valid) { if (crtc) drmModeFreeCrtc(crtc); return false; }
	uint32_t oldW = s.sourceW, oldH = s.sourceH;
	s.sourceW = width; s.sourceH = height;
	bool ok = histbDrmSetMode(crtc->mode);
	if (!ok) { s.sourceW = oldW; s.sourceH = oldH; }
	drmModeFreeCrtc(crtc);
	return ok;
}

inline bool histbEnsureOsd()
{
	auto &s = histbDrmSession();
	if (s.osdFb) return true;
	drmModeCrtcPtr crtc = drmModeGetCrtc(s.fd, s.crtc);
	if (!crtc) return false;
	bool ok = crtc->mode_valid && histbDrmSetMode(crtc->mode);
	drmModeFreeCrtc(crtc);
	return ok;
}
#endif
