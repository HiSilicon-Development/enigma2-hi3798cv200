# lib/gdi/fb.cpp SetMode: FBIOPUT_VSCREENINFO 失败时原码直接 return -1，
# 跳过了后面的 stride=fix.line_length 赋值 → stride 恒为 0 → gFBDC 按
# y*stride 算偏移整屏坍缩 → 黑屏。DVBIP-1002 的 histb-vdpdrmfb（DRM
# fbdev 仿真）连单缓冲同参数 PUT 都回 EINVAL，但默认模式就是
# 1280x720x32 可直接用。改为失败不 return，保留当前模式继续，
# 让 stride 从 FBIOGET_FSCREENINFO 正常取得。
p = 'lib/gdi/fb.cpp'
s = open(p).read()
old = ('\t\t\teDebug("[fb] FBIOPUT_VSCREENINFO %m");\n'
       '\t\t\treturn -1;\n'
       '\t\t}\n'
       '\t\teDebug("[fb] double buffering not available.");\n'
       '\t}\n'
       '\telse\n'
       '\t\teDebug("[fb] double buffering available!");')
new = ('\t\t\teDebug("[fb] FBIOPUT_VSCREENINFO %m (keep current mode)");\n'
       '\t\t}\n'
       '\t\teDebug("[fb] double buffering not available.");\n'
       '\t}\n'
       '\telse\n'
       '\t\teDebug("[fb] double buffering available!");')
if old in s:
    open(p, 'w').write(s.replace(old, new, 1))
    print('fb.cpp SetMode fallback patched')
elif '(keep current mode)' in s:
    print('fb.cpp SetMode fallback already patched')
else:
    raise SystemExit('fb.cpp anchor not found - upstream changed, review needed')

