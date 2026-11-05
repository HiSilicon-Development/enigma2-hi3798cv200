# Components/International.py：语言设置界面（LocaleSelection.
# updateLocaleList）遍历 getAvailablePackages()=DEFINED_LOCALES
# 静态全量清单（OE“语言商店”设计，列出全部可在线安装语言，
# control 文件只决定已安装标记），所以裁 po/control 不影响列表。
# 盒子无 opkg 生态，直接把清单裁成英语/简中/繁中；
# PERMANENT_LOCALES 的 de_DE 一并去掉（避免德语被当作永久已装）。
p = 'lib/python/Components/International.py'
s = open(p).read()
import re
s2 = re.sub(r'\tDEFINED_LOCALES = \[.*?\]\n',
            '\tDEFINED_LOCALES = ["en", "zh-cn", "zh-hk"]\n', s, count=1)
s2 = re.sub(r'\tPERMANENT_LOCALES = \[.*?\]\n',
            '\tPERMANENT_LOCALES = ["en_US"]\n', s2, count=1)
if s2 == s:
    if 'DEFINED_LOCALES = ["en", "zh-cn", "zh-hk"]' in s:
        print('International.py already pruned')
    else:
        raise SystemExit('International.py anchors not found - upstream changed, review needed')
else:
    open(p, 'w').write(s2)
    print('International.py DEFINED_LOCALES/PERMANENT_LOCALES pruned')

