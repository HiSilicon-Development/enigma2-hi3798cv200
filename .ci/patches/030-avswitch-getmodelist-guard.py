# AVSwitch.getModeList: DVBIP-1002 的 /proc/stb/video/* 节点全缺时
# 向导 port=None，`self.modes[port]` 直接 KeyError 把 WizardVideo
# 炸死（2026-10-29 盒子实测）。改为缺端口返回空列表，向导可走完。
p = 'lib/python/Components/AVSwitch.py'
s = open(p).read()
old = 'for mode in self.modes[port]:'
new = 'for mode in self.modes.get(port, []):'
if old in s:
    open(p, 'w').write(s.replace(old, new, 1))
    print('AVSwitch.getModeList KeyError guard patched')
elif new in s:
    print('AVSwitch.getModeList already patched')
else:
    raise SystemExit('AVSwitch.py anchor not found - upstream changed, review needed')
