# ---- /proc/stb → /var/stb（2026-10-30 盒子实测）----
# histb 内核栈不提供传统 STB 的 /proc/stb procfs 树，eAVControl
# 每次取分辨率/宽高比都刷 "Unable to open file
# '/proc/stb/vmpeg/0/xres'"（单次换台 60+ 行），写画面位置
# dst_* 同样失败。/proc 是 procfs，用户态无法在其下创建目录，
# fake 树挂载方案不可行，因此把全仓 C++/Python 的路径前缀
# 统一重定向到 /var/stb；deb 自带预填默认值的同名文件树
# （见打包段），日志静音，后续 decoder backend 可直接写真实
# 状态。纯路径字符串替换，不触碰任何逻辑。
import subprocess
r = subprocess.run(['grep', '-rl', '/proc/stb', 'lib', 'main'],
                   capture_output=True, text=True)
nfiles = 0
for f in r.stdout.split():
    s = open(f).read()
    if '/proc/stb' in s:
        open(f, 'w').write(s.replace('/proc/stb', '/var/stb'))
        nfiles += 1
print('proc-stb redirect applied to %d files' % nfiles)
