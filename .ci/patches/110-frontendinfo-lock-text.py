# Components/Converter/FrontendInfo.py：getText 对 LOCK/SLOT_NUMBER
# 类型断言失败。stock skin_default 的 Satfinder/ScanSetup 用
# Pixmap renderer + FrontendInfo>LOCK + ConditionalShowHide 组合，
# Pixmap.changed() 的 hasattr(self.source, "text") 会穿透
# ConditionalShowHide.__getattr__ 求值 text property → 断言抛出
# → 打开 Satfinder 直接 BSOD（2026-10-30 盒子实测）。
# lock/slot-number 没有有意义的文本形态，返回空串即可。
p = 'lib/python/Components/Converter/FrontendInfo.py'
s = open(p).read()
old = '\t\tassert self.type not in (self.LOCK, self.SLOT_NUMBER), "the text output of FrontendInfo cannot be used for lock info"\n'
new = ('\t\tif self.type in (self.LOCK, self.SLOT_NUMBER):\n'
       '\t\t\t# No meaningful text form for lock/slot-number. The stock\n'
       '\t\t\t# skin_default attaches Pixmap renderers to FrontendInfo>LOCK\n'
       '\t\t\t# conversions; Pixmap.changed() probes hasattr(source, "text")\n'
       '\t\t\t# which evaluates this property - raising here BSODs Satfinder.\n'
       '\t\t\treturn ""\n')
if old in s:
    open(p, 'w').write(s.replace(old, new, 1))
elif 'No meaningful text form for lock/slot-number' in s:
    print('FrontendInfo.py already patched')
else:
    raise SystemExit('FrontendInfo.py anchor not found - upstream changed, review needed')
print('FrontendInfo.py LOCK getText assert defused')

