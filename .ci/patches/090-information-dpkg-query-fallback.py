# Screens/Information.py:1357 信息界面硬编码 Popen("/usr/bin/opkg",
# "list-installed")——Debian 盒子无 opkg，直接 FileNotFoundError 崩溃
# （2026-10-30 盒子实测）。opkg 缺失时回退 dpkg-query，输出格式对齐
# opkg 的 "pkg - version"（findPackageRevision 按 "-" 切分逻辑不变）；
# 两者都没有则显示 "not found" 而非崩溃。
p = 'lib/python/Screens/Information.py'
s = open(p).read()
old = ('\t\t\tprocess = Popen(("/usr/bin/opkg", "list-installed"), stdout=PIPE, stderr=PIPE, universal_newlines=True)\n'
       '\t\t\tstdout, stderr = process.communicate()\n'
       '\t\t\tif process.returncode == 0:\n')
new = ('\t\t\tif isfile("/usr/bin/opkg"):\n'
       '\t\t\t\tprocess = Popen(("/usr/bin/opkg", "list-installed"), stdout=PIPE, stderr=PIPE, universal_newlines=True)\n'
       '\t\t\t\tstdout, stderr = process.communicate()\n'
       '\t\t\telif isfile("/usr/bin/dpkg-query"):\n'
       '\t\t\t\t# Debian box: no opkg; dpkg-query with opkg-style output ("pkg - version").\n'
       '\t\t\t\tprocess = Popen(("/usr/bin/dpkg-query", "-W", "-f=${binary:Package} - ${Version}\\n"), stdout=PIPE, stderr=PIPE, universal_newlines=True)\n'
       '\t\t\t\tstdout, stderr = process.communicate()\n'
       '\t\t\telse:\n'
       '\t\t\t\tprocess = None\n'
       '\t\t\t\tstdout, stderr = "", ""\n'
       '\t\t\tif process and process.returncode == 0:\n')
if old in s:
    open(p, 'w').write(s.replace(old, new, 1))
elif 'dpkg-query' in s:
    print('Information.py already patched')
else:
    raise SystemExit('Information.py opkg anchor not found - upstream changed, review needed')
print('Information.py opkg->dpkg-query fallback patched')
