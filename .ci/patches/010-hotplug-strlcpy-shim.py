# glibc < 2.38 无 strlcpy（OE/musl 有），注入兼容 shim
p = 'hotplug/hotplug.c'
s = open(p).read()
if 'e2_strlcpy' not in s:
    compat = '''#include <features.h>
#include <string.h>
#if defined(__GLIBC__) && !__GLIBC_PREREQ(2,38)
#define strlcpy(d, s, z) e2_strlcpy(d, s, z)
static inline size_t e2_strlcpy(char *dst, const char *src, size_t size) {
	size_t len = strlen(src);
	if (size) { size_t n = (len >= size) ? size - 1 : len; memcpy(dst, src, n); dst[n] = 0; }
	return len;
}
#endif
'''
    open(p, 'w').write(compat + s)
    print('strlcpy shim injected')
else:
    print('shim already present')
