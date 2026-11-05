# Screens/SoftwareUpdate.py:214 无 opkg 时 getFetchedList 返回短元组，
# fetched[1] 直接 IndexError → FATAL SIGNAL（2026-10-30 盒子实测）。
# 跳过字段不足的条目，界面落入 noupdate/error 状态而非崩溃。
p = 'lib/python/Screens/SoftwareUpdate.py'
s = open(p).read()
old = ('\t\t\t\t\tfor fetched in fetchedList:\n'
       '\t\t\t\t\t\toldVer = fetched[1] if fetched[1] else _("Current version unknown")\n')
new = ('\t\t\t\t\tfor fetched in fetchedList:\n'
       '\t\t\t\t\t\tif len(fetched) < 3:\n'
       '\t\t\t\t\t\t\tcontinue\n'
       '\t\t\t\t\t\toldVer = fetched[1] if fetched[1] else _("Current version unknown")\n')
if old in s:
    open(p, 'w').write(s.replace(old, new, 1))
elif 'len(fetched) < 3' in s:
    print('SoftwareUpdate.py already patched')
else:
    raise SystemExit('SoftwareUpdate.py anchor not found - upstream changed, review needed')
print('SoftwareUpdate.py short-tuple guard patched')

