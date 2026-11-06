# main/enigma.cpp: 盒子 Debian 无 glibc UTF-8 locale，内嵌 Python
# locale 回退 POSIX → open() 默认 ascii → fileReadLines 读自带
# groupedservices（含 UTF-8 字节）时 UnicodeDecodeError，InfoBar
# 启动即 exit 5（2026-10-29 盒子实测）。强制 PYTHONUTF8=1
# （PEP 540 UTF-8 模式），open()/stdio 默认 UTF-8，等同 OE 镜像
# 有真实 UTF-8 locale 的效果。
p = 'main/enigma.cpp'
s = open(p).read()
old = '\tsetenv("PYTHONPATH", eEnv::resolve("${libdir}/enigma2/python").c_str(), 0);\n'
new = (old
       + '\t// Force Python UTF-8 mode: host lacks glibc UTF-8 locales,\n'
         '\t// so open() would default to ascii and crash on UTF-8 data files.\n'
         '\tsetenv("PYTHONUTF8", "1", 1);\n')
if s.count(new) == 1:
    print('enigma.cpp already patched')
elif s.count(old) == 1:
    open(p, 'w').write(s.replace(old, new, 1))
    print('enigma.cpp PYTHONUTF8 patched')
else:
    raise SystemExit('enigma.cpp anchor not found - upstream changed, review needed')
