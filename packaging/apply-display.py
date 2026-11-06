#!/usr/bin/env python3
"""Apply the HiSTB KMS display integration to an Enigma2 source tree.

Usage: apply-display.py PATH_TO_ENIGMA2
Run after generic Debian adaptations and before the /proc/stb redirect.
This script installs the reviewed native KMS headers and AVControl backend.
The maintained display-mode-geometry patch supplies the fbdev/skin policy;
there is no generated CPU OSD scaling or pixel-copy hook.
Header installation and backend injection are safe to repeat.
"""
import os
from pathlib import Path
import shutil
import sys

packaging = Path(__file__).resolve().parent
os.chdir(Path(sys.argv[1]).resolve())

# Shared KMS master, native-depth video and EDID mode control.
# Keep implementation in reviewed headers rather than generated C++.
for header in ('histb_drm.h', 'avcontrol_histb_impl.h'):
    shutil.copyfile(packaging / header, 'lib/driver/' + header)
# Keep the matching project-local modifier contract beside its consumer.
shutil.copytree(packaging / 'uapi', 'lib/driver/uapi', dirs_exist_ok=True)
p = 'lib/driver/avcontrol.cpp'
s = open(p).read()
if 'avcontrol_histb_impl.h' in s:
    print('avcontrol.cpp histb videomode backend already patched')
else:
    helpers = '#ifdef HAVE_HISTB\n#include <lib/driver/avcontrol_histb_impl.h>\n#endif\n'
    anchor = 'eAVControl *eAVControl::m_instance = nullptr;'
    if anchor not in s:
        raise SystemExit('avcontrol.cpp m_instance anchor not found')
    s = s.replace(anchor, helpers + '\n' + anchor, 1)

    anchor = '\tstd::string driverMode = getDriverVideoMode(newMode);\n'
    new = (anchor
           + '#ifdef HAVE_HISTB\n'
             '\tif (histbSetVideoMode(newMode, flags))\n'
             '\t\tCFile::writeStr(proc_videomode, driverMode, __MODULE__, flags);\n'
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
           '\treturn histbGetVideoMode();\n'
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

    for signature in ('readAvailableModes(int flags)', 'getPreferredModes(int flags)', 'getAvailableModes()'):
        anchor = 'std::string eAVControl::' + signature + ' const\n{\n'
        if anchor not in s:
            raise SystemExit('avcontrol.cpp mode query anchor not found: ' + signature)
        new = anchor + '#ifdef HAVE_HISTB\n\treturn histbReadEdidModes();\n#endif\n'
        s = s.replace(anchor, new, 1)

    open(p, 'w').write(s)
    print('avcontrol.cpp histb videomode backend patched')

