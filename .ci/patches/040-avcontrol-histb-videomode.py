# avcontrol.cpp: HAVE_HISTB 真实视频模式后端（2026-11-03）。
# /var/stb/video/videomode 是假文件，写它不切显示模式 → 设置里
# 选 720p/1080p 无任何反应（盒子实测）。真后端：模式列表从 DRM
# connector EDID 枚举（只读 ioctl，无需 DRM master）；应用走
# fb0 FBIOPUT_VSCREENINFO，由内核 drm fbdev helper 执行。
# 盒子实测：helper 切 CRTC 模式时 fb0 buffer 尺寸保持不变
# （enigma2 的 mmap 持续有效，OSD plane 被拉伸到新模式）。
p = 'lib/driver/avcontrol.cpp'
s = open(p).read()
if 'histbReadEdidModes' in s:
    print('avcontrol.cpp histb videomode backend already patched')
else:
    helpers = r'''
#ifdef HAVE_HISTB
/* histb real video mode backend: the kernel has no traditional STB
 * procfs video tree, the fake files cannot switch the display.
 * Enumerate modes from the DRM connector EDID (read-only ioctls, no
 * DRM master needed) and apply through FBIOPUT_VSCREENINFO on fb0,
 * executed by the in-kernel drm fbdev helper. */
#include <algorithm>
#include <fcntl.h>
#include <unistd.h>
#include <sys/ioctl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <linux/fb.h>
#include <vector>
#include <xf86drm.h>
#include <xf86drmMode.h>

struct HistbModeSpec
{
	int w = 0, h = 0, refresh = 0;
	bool interlaced = false;
};

static int histbOpenHdmiCard(drmModeResPtr *resOut, drmModeConnectorPtr *connOut)
{
	for (int i = 0; i < 8; ++i)
	{
		char path[32];
		snprintf(path, sizeof(path), "/dev/dri/card%d", i);
		int fd = open(path, O_RDWR | O_CLOEXEC);
		if (fd < 0)
			continue;
		drmModeResPtr res = drmModeGetResources(fd);
		if (!res)
		{
			close(fd);
			continue;
		}
		for (int c = 0; c < res->count_connectors; ++c)
		{
			drmModeConnectorPtr conn = drmModeGetConnector(fd, res->connectors[c]);
			if (!conn)
				continue;
			if (conn->connection == DRM_MODE_CONNECTED && conn->count_modes > 0)
			{
				*resOut = res;
				*connOut = conn;
				return fd;
			}
			drmModeFreeConnector(conn);
		}
		drmModeFreeResources(res);
		close(fd);
	}
	return -1;
}

/* enigma2 AVSwitch.rates naming: base name == 60Hz for
 * 720p/1080i/1080p/2160p/smpte, == 50Hz for 576i/576p and 60Hz for
 * 480i/480p; other refresh rates get a numeric suffix */
static bool histbModeName(const drmModeModeInfo &m, std::string &name)
{
	if (!m.clock)
		return false;
	bool interlaced = (m.flags & DRM_MODE_FLAG_INTERLACE) != 0;
	const char *base = nullptr;
	int expect = 60;
	if (m.hdisplay == 1280 && m.vdisplay == 720 && !interlaced)
		base = "720p";
	else if (m.hdisplay == 1920 && m.vdisplay == 1080 && interlaced)
		base = "1080i";
	else if (m.hdisplay == 1920 && m.vdisplay == 1080 && !interlaced)
		base = "1080p";
	else if (m.hdisplay == 3840 && m.vdisplay == 2160 && !interlaced)
		base = "2160p";
	else if (m.hdisplay == 4096 && m.vdisplay == 2160 && !interlaced)
		base = "smpte";
	else if (m.hdisplay == 720 && m.vdisplay == 576 && interlaced)
	{
		base = "576i";
		expect = 50;
	}
	else if (m.hdisplay == 720 && m.vdisplay == 576 && !interlaced)
	{
		base = "576p";
		expect = 50;
	}
	else if (m.hdisplay == 720 && m.vdisplay == 480 && interlaced)
		base = "480i";
	else if (m.hdisplay == 720 && m.vdisplay == 480 && !interlaced)
		base = "480p";
	if (!base)
		return false;
	if ((int)m.vrefresh != expect)
		name = std::string(base) + std::to_string((int)m.vrefresh);
	else
		name = base;
	return true;
}

static std::string histbReadEdidModes()
{
	drmModeResPtr res = nullptr;
	drmModeConnectorPtr conn = nullptr;
	int fd = histbOpenHdmiCard(&res, &conn);
	if (fd < 0)
		return "";
	std::vector<std::string> names;
	for (int m = 0; m < conn->count_modes; ++m)
	{
		std::string name;
		if (!histbModeName(conn->modes[m], name))
			continue;
		if (std::find(names.begin(), names.end(), name) == names.end())
			names.push_back(name);
	}
	drmModeFreeConnector(conn);
	drmModeFreeResources(res);
	close(fd);
	std::string result;
	for (const auto &n : names)
	{
		if (!result.empty())
			result += ' ';
		result += n;
	}
	return result;
}

static bool histbParseModeName(const std::string &modeName, HistbModeSpec &spec)
{
	if (modeName == "pal")
	{
		spec = {720, 576, 50, true};
		return true;
	}
	if (modeName == "ntsc")
	{
		spec = {720, 480, 60, true};
		return true;
	}
	if (modeName == "pal60")
	{
		spec = {720, 576, 60, true};
		return true;
	}
	static const struct
	{
		const char *name;
		int w, h, refresh;
		bool il;
	} bases[] = {
		{"smpte", 4096, 2160, 60, false},
		{"2160p", 3840, 2160, 60, false},
		{"1080p", 1920, 1080, 60, false},
		{"1080i", 1920, 1080, 60, true},
		{"720p", 1280, 720, 60, false},
		{"576p", 720, 576, 50, false},
		{"576i", 720, 576, 50, true},
		{"480p", 720, 480, 60, false},
		{"480i", 720, 480, 60, true},
	};
	for (const auto &b : bases)
	{
		size_t n = strlen(b.name);
		if (modeName.compare(0, n, b.name) != 0)
			continue;
		std::string rest = modeName.substr(n);
		if (!rest.empty() && rest.find_first_not_of("0123456789") != std::string::npos)
			continue;
		spec.w = b.w;
		spec.h = b.h;
		spec.interlaced = b.il;
		spec.refresh = rest.empty() ? b.refresh : atoi(rest.c_str());
		return true;
	}
	return false;
}

static bool histbFindDrmMode(drmModeConnectorPtr conn, const HistbModeSpec &spec, drmModeModeInfo &out)
{
	const drmModeModeInfo *best = nullptr;
	for (int i = 0; i < conn->count_modes; ++i)
	{
		const drmModeModeInfo &m = conn->modes[i];
		if ((int)m.hdisplay != spec.w || (int)m.vdisplay != spec.h)
			continue;
		if (((m.flags & DRM_MODE_FLAG_INTERLACE) != 0) != spec.interlaced)
			continue;
		if (!best || (spec.refresh && (int)m.vrefresh == spec.refresh))
			best = &m;
	}
	if (!best)
		return false;
	out = *best;
	return true;
}

static bool histbApplyMode(const HistbModeSpec &spec)
{
	drmModeResPtr res = nullptr;
	drmModeConnectorPtr conn = nullptr;
	int fd = histbOpenHdmiCard(&res, &conn);
	if (fd < 0)
	{
		eDebug("[eAVControl] histb: no connected DRM card found");
		return false;
	}
	drmModeModeInfo mode = {};
	bool found = histbFindDrmMode(conn, spec, mode);
	drmModeFreeConnector(conn);
	drmModeFreeResources(res);
	close(fd);
	if (!found)
	{
		eDebug("[eAVControl] histb: %dx%d%s@%d not in EDID modes", spec.w, spec.h, spec.interlaced ? "i" : "p", spec.refresh);
		return false;
	}

	int fb = open("/dev/fb0", O_RDWR | O_CLOEXEC);
	if (fb < 0)
	{
		eDebug("[eAVControl] histb: fb0 open failed: %s", strerror(errno));
		return false;
	}
	struct fb_var_screeninfo v = {};
	if (ioctl(fb, FBIOGET_VSCREENINFO, &v) < 0)
	{
		eDebug("[eAVControl] histb: FBIOGET failed: %s", strerror(errno));
		close(fb);
		return false;
	}
	/* keep xres/yres_virtual from GET: the driver's fbdev helper
	 * owns the buffer geometry, only the scanout timing changes */
	v.xres = mode.hdisplay;
	v.yres = mode.vdisplay;
	v.xoffset = v.yoffset = 0;
	v.pixclock = mode.clock ? 1000000000U / (unsigned)mode.clock : 0;
	v.left_margin = mode.htotal - mode.hsync_end;
	v.right_margin = mode.hsync_start - mode.hdisplay;
	v.hsync_len = mode.hsync_end - mode.hsync_start;
	v.upper_margin = mode.vtotal - mode.vsync_end;
	v.lower_margin = mode.vsync_start - mode.vdisplay;
	v.vsync_len = mode.vsync_end - mode.vsync_start;
	v.sync = ((mode.flags & DRM_MODE_FLAG_PHSYNC) ? FB_SYNC_HOR_HIGH_ACT : 0) | ((mode.flags & DRM_MODE_FLAG_PVSYNC) ? FB_SYNC_VERT_HIGH_ACT : 0);
	v.vmode = (mode.flags & DRM_MODE_FLAG_INTERLACE) ? FB_VMODE_INTERLACED : FB_VMODE_NONINTERLACED;
	v.activate = FB_ACTIVATE_FORCE;
	v.nonstd = 0;
	int ret = ioctl(fb, FBIOPUT_VSCREENINFO, &v);
	if (ret < 0)
		eDebug("[eAVControl] histb: FBIOPUT %dx%d@%d failed: %s (virtual %ux%u)", mode.hdisplay, mode.vdisplay, spec.refresh, strerror(errno), v.xres_virtual, v.yres_virtual);
	close(fb);
	return ret == 0;
}

static bool histbSetVideoMode(const std::string &modeName, int flags)
{
	(void)flags;
	HistbModeSpec spec;
	if (!histbParseModeName(modeName, spec))
	{
		eDebug("[eAVControl] histb: cannot parse video mode '%s'", modeName.c_str());
		return false;
	}
	bool ok = histbApplyMode(spec);
	if (ok)
		eDebug("[eAVControl] histb: video mode %s applied (%dx%d%s@%d)", modeName.c_str(), spec.w, spec.h, spec.interlaced ? "i" : "p", spec.refresh);
	else
		eWarning("[eAVControl] histb: video mode %s could not be applied", modeName.c_str());
	return ok;
}

static std::string histbGetVideoMode()
{
	FILE *f = fopen("/sys/class/graphics/fb0/mode", "r");
	if (!f)
		return "";
	char line[128] = {};
	const char *got = fgets(line, sizeof(line), f);
	fclose(f);
	if (!got)
		return "";
	char scan = 0;
	int w = 0, h = 0, r = 0;
	if (sscanf(line, "%*c:%dx%d%c-%d", &w, &h, &scan, &r) != 4)
		return "";
	bool il = scan == 'i';
	const char *base = nullptr;
	int expect = 60;
	if (w == 1280 && h == 720 && !il)
		base = "720p";
	else if (w == 1920 && h == 1080 && il)
		base = "1080i";
	else if (w == 1920 && h == 1080 && !il)
		base = "1080p";
	else if (w == 3840 && h == 2160 && !il)
		base = "2160p";
	else if (w == 4096 && h == 2160 && !il)
		base = "smpte";
	else if (w == 720 && h == 576)
	{
		base = il ? "576i" : "576p";
		expect = 50;
	}
	else if (w == 720 && h == 480)
		base = il ? "480i" : "480p";
	if (!base)
		return "";
	if ((w == 720 && r != expect) || (w != 720 && r != 60))
		return std::string(base) + std::to_string(r);
	return base;
}
#endif /* HAVE_HISTB */
'''
    anchor = 'eAVControl *eAVControl::m_instance = nullptr;'
    if anchor not in s:
        raise SystemExit('avcontrol.cpp m_instance anchor not found')
    s = s.replace(anchor, helpers + '\n' + anchor, 1)

    anchor = '\tstd::string driverMode = getDriverVideoMode(newMode);\n'
    new = (anchor
           + '#ifdef HAVE_HISTB\n'
             '\t/* keep the fake file in sync (getVideoMode fallback), then do\n'
             '\t * the real switch through fb0 - nothing reads it back here */\n'
             '\tCFile::writeStr(proc_videomode, driverMode, __MODULE__, flags);\n'
             '\thistbSetVideoMode(newMode, flags);\n'
             '\treturn;\n'
             '#endif\n')
    if anchor not in s:
        raise SystemExit('avcontrol.cpp setVideoMode anchor not found')
    s = s.replace(anchor, new, 1)

    anchor = ('std::string eAVControl::getVideoMode(const std::string &defaultVal, int flags) const\n'
              '{\n'
              '#ifdef VIDEO_MODE_50\n')
    new = ('std::string eAVControl::getVideoMode(const std::string &defaultVal, int flags) const\n'
           '{\n'
           '#ifdef HAVE_HISTB\n'
           '\t{\n'
           '\t\tstd::string current = histbGetVideoMode();\n'
           '\t\tif (!current.empty())\n'
           '\t\t\treturn current;\n'
           '\t}\n'
           '#endif\n'
           '#ifdef VIDEO_MODE_50\n')
    if anchor not in s:
        raise SystemExit('avcontrol.cpp getVideoMode anchor not found')
    s = s.replace(anchor, new, 1)

    anchor = ('void eAVControl::setVideoModeMulti(const std::string &mode50, const std::string &mode60, const std::string &mode24, int flags) const\n'
              '{\n'
              '#ifdef DREAMNEXTGEN\n')
    new = ('void eAVControl::setVideoModeMulti(const std::string &mode50, const std::string &mode60, const std::string &mode24, int flags) const\n'
           '{\n'
           '#ifdef HAVE_HISTB\n'
           '\tsetVideoMode(!mode50.empty() ? mode50 : (!mode60.empty() ? mode60 : mode24), flags);\n'
           '\treturn;\n'
           '#endif\n'
           '#ifdef DREAMNEXTGEN\n')
    if anchor not in s:
        raise SystemExit('avcontrol.cpp setVideoModeMulti anchor not found')
    s = s.replace(anchor, new, 1)

    anchor = ('\tconst char *fileName = "/proc/stb/video/videomode_choices";\n'
              '\tstd::string result = "";\n'
              '\tif (access(fileName, R_OK) == 0)\n'
              '\t{\n'
              '\t\tresult = CFile::read(fileName, __MODULE__, flags);\n'
              '\t}\n')
    new = ('\tstd::string result = histbReadEdidModes();\n'
           '\tif (result.empty())\n'
           '\t{\n'
           '\t\tconst char *fileName = "/proc/stb/video/videomode_choices";\n'
           '\t\tif (access(fileName, R_OK) == 0)\n'
           '\t\t\tresult = CFile::read(fileName, __MODULE__, flags);\n'
           '\t}\n')
    if anchor not in s:
        raise SystemExit('avcontrol.cpp readAvailableModes anchor not found')
    s = s.replace(anchor, new, 1)

    open(p, 'w').write(s)
    print('avcontrol.cpp histb videomode backend patched')

