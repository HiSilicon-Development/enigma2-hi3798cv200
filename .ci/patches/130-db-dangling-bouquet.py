# ---- lib/dvb/db.cpp：悬空 bouquet 条目修复 ----
# loadBouquet() 在检查引用文件是否存在之前就执行
# m_bouquets[bouquet_name]（operator[] 默认构造空 eBouquet，
# m_bouquet_name=""）。被引用的 userbouquet 文件缺失时函数
# return，但空条目已留在 map：① 名字解析
# （eStaticServiceDVBBouquetInformation::getName）见空名返回 -1，
# 频道列表直接显示 FROM BOUQUET "xxx" 原文（2026-10-30 盒子实测，
# bouquets.tv 有 favourites 条目而 userbouquet.favourites.tv
# 缺失）；② reloadBouquets() 的 favourites 自动补建分支因
# find() 命中空条目而永不执行，文件永远补不上。修复：未找到
# 文件时 erase 掉 operator[] 产生的空条目，让补建逻辑生效。
#
# 2026-11-07: upstream 把 loadBouquet 改成返回 bool（缺文件返回
# false，truncated 检测复用同一返回值），空条目问题不变，故两种
# 返回形式都要适配。
p = 'lib/dvb/db.cpp'
s = open(p).read()

debug = 'eDebug("[eDVBDB] Error: Can\'t load bouquet \'%s\'!", path);\n'
erase = '\t\t\t\tm_bouquets.erase(bouquet_name);\n'
variants = ('\t\t\t\treturn false;\n', '\t\t\t\treturn;\n')

if 'm_bouquets.erase(bouquet_name)' in s:
    print('db.cpp dangling bouquet entry fixed')
else:
    for ret in variants:
        old = debug + ret
        if s.count(old) == 1:
            s = s.replace(old, debug + erase + ret, 1)
            open(p, 'w').write(s)
            print('db.cpp dangling bouquet entry fixed (%s)' % ret.strip())
            break
    else:
        raise SystemExit('db.cpp missing-bouquet anchor not found - upstream changed, review needed')
