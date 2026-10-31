# ---- lib/dvb/demux.cpp：DMX_SET_SOURCE 失败也记录 source ----
# histb-dmx 不实现 DMX_SET_SOURCE（该 ioctl 内核 4.14+ 已从主线
# 移除，openatv 只给 UAPI 打了 shim，驱动没有实现 → ENOTTY）。
# setSourceFrontend() 仅在 ioctl 成功时置 source=fenum，失败时
# source 保持 -1；allocateDemux() 的占用共享判定要求
# getSource()==前端 DVBID，永远不成立 → 每个 adapter 只有一个
# demux 且已被同频道的 cap=00（数据 demux）占住，cap=01（解码
# demux）共享失败 → "no free demux found"，所有调谐器直播无法
# 起播（2026-10-30 盒子 8922 会话实测：09:45:05 cap=00 成功 +
# DMX_SET_SOURCE Frontend4 failed，09:45:15 cap=01 no free
# demux found）。本机每 adapter 一前端一 demux，DMX_SET_SOURCE
# 的硬件路由本就是空操作，软件记账即可。
p = 'lib/dvb/demux.cpp'
s = open(p).read()
old = ('eDebug("[eDVBDemux] DMX_SET_SOURCE Frontend%d failed: %m", fenum);\n'
       '\telse\n'
       '\t\tsource = fenum;\n')
new = ('eDebug("[eDVBDemux] DMX_SET_SOURCE Frontend%d failed: %m", fenum);\n'
       '\t/* DVBIP-1002: histb-dmx has no DMX_SET_SOURCE (ENOTTY) and\n'
       '\t * each adapter has a single frontend and demux, so hardware\n'
       '\t * source routing is a no-op. Record the source anyway:\n'
       '\t * allocateDemux() sharing (getSource() == frontend DVBID)\n'
       '\t * must succeed for live decode-demux allocation on the\n'
       '\t * single demux of each adapter. */\n'
       '\tsource = fenum;\n')
if old in s:
    s = s.replace(old, new, 1)
elif 'allocateDemux() sharing (getSource() == frontend DVBID)' in s:
    pass
else:
    raise SystemExit('demux.cpp setSourceFrontend anchor not found - upstream changed, review needed')
open(p, 'w').write(s)
print('demux.cpp setSourceFrontend fallback patched')
