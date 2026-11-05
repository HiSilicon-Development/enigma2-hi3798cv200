# ---- histb 软件 decoder backend（2026-10-30）----
# histb 内核栈没有 DVB video/audio decoder 设备节点
# (/dev/dvb/adapterN/{video,audio}0)，直播解码走：
#   demux PES tap -> 用户态 TS/PES 拆包 -> hivxe-ffmpeg
#   (v4l2request hwaccel: AVS+/CAVS, H264, HEVC, MPEG2)
#   -> DRM_PRIME dmabuf -> histb-vdp DRM overlay plane
# 音频 -> avcodec (MP2/AAC/AC3/DTS/EAC3) -> swresample -> ALSA。
# hivxe-ffmpeg 头取自 HiSilicon-Development/FFmpeg fork（与
# extra 安装件的 avcodec 63.1.101 同源），运行时 dlopen 不硬链接。

import os
import shutil

# Install every local backend dependency even when the source is already wired.
packaging = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'packaging')
for header in ('decoder_histb_impl.h', 'histb_video_capture_impl.h',
               'histb_audio_control.h'):
    shutil.copy(os.path.join(packaging, header), os.path.join('lib/dvb', header))

# Source wiring is independent of the refreshed implementation headers.
decoder = open('lib/dvb/decoder.cpp').read()
if '#include <lib/dvb/decoder_histb_impl.h>' in decoder:
    header = open('lib/dvb/decoder.h').read()
    required = ('#ifdef HAVE_HISTB\n#include <lib/dvb/decoder_histb_impl.h>\n#else\nDEFINE_REF(eDVBAudio);',
                '#endif /* HAVE_HISTB */\n\nDEFINE_REF(eTSMPEGDecoder);',
                '#ifdef HAVE_HISTB\n\t\tm_has_audio = true;\n#endif')
    if header.count('void *m_histb = nullptr;') != 4 or any(decoder.count(anchor) != 1 for anchor in required):
        raise SystemExit('decoder histb wiring incomplete - upstream changed, review needed')
    print('decoder histb backend already wired')
    import sys
    sys.exit(0)

p = 'lib/dvb/decoder.h'
s = open(p).read()
old = 'int m_fd, m_fd_demux, m_dev, m_is_freezed, m_bypass;'
assert s.count(old) == 1, 'eDVBAudio pimpl anchor'
s = s.replace(old, old + '\n\tvoid *m_histb = nullptr;', 1)
old = 'int m_fd, m_fd_demux, m_dev;'
assert s.count(old) == 1, 'eDVBVideo pimpl anchor'
s = s.replace(old, old + '\n\tvoid *m_histb = nullptr;', 1)
old = 'int m_fd_demux, m_dev;'
assert s.count(old) == 2, 'eDVBPCR/eDVBTText pimpl anchor'
s = s.replace(old, old + '\n\tvoid *m_histb = nullptr;')
open(p, 'w').write(s)
print('decoder.h pimpl members added')

p = 'lib/dvb/decoder.cpp'
s = open(p).read()
old = 'DEFINE_REF(eDVBAudio);'
assert s.count(old) == 1
s = s.replace(old,
    '#ifdef HAVE_HISTB\n'
    '#include <lib/dvb/decoder_histb_impl.h>\n'
    '#else\n' + old, 1)
old = 'DEFINE_REF(eTSMPEGDecoder);'
assert s.count(old) == 1
s = s.replace(old,
    '#endif /* HAVE_HISTB */\n\n' + old, 1)
# The #ifdef/#else span excludes the file-scope VIDEO_STREAMTYPE_*
# defines (needed by eTSMPEGDecoder below); relocate the block above
# the sandwich so both build paths see it.
start_anchor = '// not finally values i think.. !!'
assert s.count(start_anchor) == 1, 'streamtype comment anchor'
i0 = s.index(start_anchor)
j = s.index('#define VIDEO_STREAMTYPE_AVS2', i0)
i1 = s.index('#endif', j) + len('#endif')
i1 = s.index('\n', i1) + 1
block = s[i0:i1]
s = s[:i0] + s[i1:]
anchor = '#ifdef HAVE_HISTB\n#include <lib/dvb/decoder_histb_impl.h>'
assert s.count(anchor) == 1, 'histb include anchor'
s = s.replace(anchor, block + '\n' + anchor, 1)
# histb backend implements audio via ALSA; the box has no legacy
# DVB /dev/dvb/adapterN/audioN device node, so m_has_audio stays
# false and setAudioPID() silently forces apid=-1. Force it on.
old = 'm_has_audio = !access(filename, W_OK);'
assert s.count(old) == 1, 'm_has_audio anchor'
s = s.replace(old,
    old + '\n'
    '#ifdef HAVE_HISTB\n'
    '\t\tm_has_audio = true;\n'
    '#endif', 1)
depth = 0
for line in s.split('\n'):
    st = line.strip()
    if st.startswith('#ifdef') or st.startswith('#ifndef') or st.startswith('#if '):
        depth += 1
    elif st.startswith('#endif'):
        depth -= 1
assert depth == 0, 'unbalanced ifdefs depth %d' % depth
open(p, 'w').write(s)
print('decoder.cpp histb backend wired')
