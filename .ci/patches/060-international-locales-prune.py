# Components/International.py：语言设置界面（LocaleSelection.
# updateLocaleList）遍历 getAvailablePackages()=DEFINED_LOCALES
# 静态全量清单（OE“语言商店”设计，列出全部可在线安装语言，
# control 文件只决定已安装标记），所以裁 po/control 不影响列表。
# 盒子无 opkg 生态，直接把清单裁成英语/简中/繁中；
# PERMANENT_LOCALES 的 de_DE 一并去掉（避免德语被当作永久已装）。
p = 'lib/python/Components/International.py'
s = open(p).read()
import re
for name, value in (('DEFINED_LOCALES', '["en", "zh-cn", "zh-hk"]'),
                    ('PERMANENT_LOCALES', '["en_US"]')):
    replacement = '\t' + name + ' = ' + value + '\n'
    pattern = r'\t' + name + r' = \[.*?\]\n'
    s, count = re.subn(pattern, replacement, s)
    if count != 1:
        raise SystemExit('International.py ' + name + ' anchor not unique - upstream changed, review needed')
open(p, 'w').write(s)
print('International.py DEFINED_LOCALES/PERMANENT_LOCALES pruned')
