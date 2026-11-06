# Tools/Directories.py：所有文本读写不指定编码，跟随 locale 默认值。
# 盒子无 glibc UTF-8 locale 时 Python 退回 ascii，自带数据文件
# （groupedservices 等）含 UTF-8 字节即 UnicodeDecodeError →
# InfoBar 启动 exit 5。实测 PYTHONUTF8=1 环境变量在嵌入式解释器上
# 不稳定（run35 有效、run37 复崩），改为读写全部显式 UTF-8（确定性）。
p = 'lib/python/Tools/Directories.py'
s = open(p).read()
replacements = [
    ('with open(filename) as fd:', 'with open(filename, encoding="utf-8") as fd:'),
    ('with open(filename, "w") as fd:', 'with open(filename, "w", encoding="utf-8") as fd:'),
]
count = sum(s.count(old) for old, new in replacements)
applied = sum(s.count(new) for old, new in replacements)
if count == 0 and applied >= 5:
    print('Directories.py already pinned to utf-8')
elif count >= 5:
    for old, new in replacements:
        s = s.replace(old, new)
    open(p, 'w').write(s)
    print(f'Directories.py: {count} open() calls pinned to utf-8')
else:
    raise SystemExit(f'Directories.py open anchors: expected >=5, got {count} - upstream changed, review needed')
