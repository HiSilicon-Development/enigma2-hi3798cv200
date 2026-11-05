#ifndef E2_AVCONTROL_HISTB_IMPL_H
#define E2_AVCONTROL_HISTB_IMPL_H
#include <cstdlib>
#include <string>
#include <vector>
#include <lib/driver/histb_drm.h>
struct HistbModeSpec
{
 int w = 0, h = 0, refresh = 0;
 bool interlaced = false;
};

static int histbModeRefresh(const drmModeModeInfo &mode)
{
	double period = histbDrmModePeriodUs(mode);
	return period > 0 ? int(1000000.0 / period + 0.5) : 0;
}
/* Match AVSwitch.rates: 60 Hz uses a bare name except smpte60;
 * 576i/p defaults to 50 Hz. Other rates have an explicit suffix. */
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
	int refresh = histbModeRefresh(m);
	if (refresh != expect || m.hdisplay == 4096)
		name = std::string(base) + std::to_string(refresh);
	else
		name = base;
	return true;
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
		if (histbModeRefresh(m) == spec.refresh && (!best || (m.type & DRM_MODE_TYPE_PREFERRED)))
			best = &m;
	}
	if (!best)
		return false;
	out = *best;
	return true;
}


/* KMS may supply conservative fallback modes when no valid sink EDID exists.
 * Those are not display capabilities and must not enter selection or apply. */
static bool histbHasEdid(drmModeConnectorPtr conn)
{
 uint64_t blob = 0;
 auto &s = histbDrmSession();
 return conn->connection == DRM_MODE_CONNECTED &&
  histbDrmProperty(s.fd, conn->connector_id, DRM_MODE_OBJECT_CONNECTOR, "EDID", &blob) && blob;
}

static std::string histbReadEdidModes()
{
 auto &s = histbDrmSession();
 std::lock_guard<std::mutex> lock(s.mutex);
 if (histbDrmOpen() < 0) return "";
 drmModeConnectorPtr conn = drmModeGetConnector(s.fd, s.connector);
 if (!conn || !histbHasEdid(conn)) { if (conn) drmModeFreeConnector(conn); return ""; }
 std::vector<std::string> names;
 std::string result;
 for (int i = 0; i < conn->count_modes; ++i)
 {
  std::string name;
  if (histbModeName(conn->modes[i], name) && std::find(names.begin(), names.end(), name) == names.end())
  {
   if (!result.empty()) result += ' ';
   result += name; names.push_back(name);
  }
 }
 drmModeFreeConnector(conn);
 return result;
}

static bool histbSetVideoMode(const std::string &name, int flags)
{
 (void)flags;
 HistbModeSpec spec;
 if (!histbParseModeName(name, spec)) return false;
 auto &s = histbDrmSession();
 std::lock_guard<std::mutex> lock(s.mutex);
 if (histbDrmOpen() < 0) return false;
 drmModeConnectorPtr conn = drmModeGetConnector(s.fd, s.connector);
 if (!conn) return false;
 drmModeModeInfo mode = {};
 bool ok = histbHasEdid(conn) && histbFindDrmMode(conn, spec, mode);
 drmModeFreeConnector(conn);
 if (ok) ok = histbDrmSetMode(mode);
 if (ok) eDebug("[eAVControl] histb: %s applied (%dx%d @ %d)", name.c_str(), spec.w, spec.h, spec.refresh);
 else eWarning("[eAVControl] histb: mode %s not applied; query KMS for the active mode", name.c_str());
 return ok;
}

static std::string histbGetVideoMode()
{
 auto &s = histbDrmSession();
 std::lock_guard<std::mutex> lock(s.mutex);
 if (histbDrmOpen() < 0) return "";
 drmModeCrtcPtr crtc = drmModeGetCrtc(s.fd, s.crtc);
 std::string name;
 if (crtc && crtc->mode_valid) histbModeName(crtc->mode, name);
 if (crtc) drmModeFreeCrtc(crtc);
 return name;
}
#endif
