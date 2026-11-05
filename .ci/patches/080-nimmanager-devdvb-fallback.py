# Components/NimManager.py：调谐器枚举唯一数据源是
# /proc/bus/nim_sockets（Dreambox 专有接口，由各厂商私有驱动提供）。
# Hi3798CV200 mainline DVB 驱动（histb-dmx + mxl214，4x DVB-C）
# 只注册标准 /dev/dvb/adapterN/frontend0，无任何 proc 文件 →
# 调谐器列表为空（2026-10-30 盒子实测）。补回退枚举：
# /proc/bus/nim_sockets 缺失时用 ctypes FE_GET_INFO 扫描
# /dev/dvb/adapter*/frontend0，entries 与 proc 解析格式一致，
# 复用同一段 NIM 构建管线（late-slot/fbc/input_name 逻辑不变）。
p = 'lib/python/Components/NimManager.py'
s = open(p).read()
old = ('\t\ttry:\n'
       '\t\t\tnimfile = open("/proc/bus/nim_sockets")\n'
       '\t\texcept OSError:\n'
       '\t\t\treturn\n'
       '\t\tcurrent_slot = None\n'
       '\t\tentries = {}\n'
       '\t\tfor line in nimfile:\n')
new = ('\t\tentries = self.enumDevDvbFrontends()\n'
       '\t\tif entries is None:\n'
       '\t\t\ttry:\n'
       '\t\t\t\tnimfile = open("/proc/bus/nim_sockets")\n'
       '\t\t\texcept OSError:\n'
       '\t\t\t\treturn\n'
       '\t\t\tentries = {}\n'
       '\t\tcurrent_slot = None\n'
       '\t\tfor line in nimfile if entries is None else []:\n')
old_close = '\t\tnimfile.close()\n'
new_close = '\t\tif entries is None:\n\t\t\tnimfile.close()\n'
if old not in s and 'enumDevDvbFrontends' not in s:
    raise SystemExit('NimManager.py enumerateNIMs anchor not found - upstream changed, review needed')
if old in s:
    s = s.replace(old, new, 1)
    if s.count(old_close) != 1:
        raise SystemExit('NimManager.py nimfile.close anchor not unique - upstream changed, review needed')
    s = s.replace(old_close, new_close, 1)
    anchor = '\tdef enumerateNIMs(self):\n'
    if s.count(anchor) != 1:
        raise SystemExit('NimManager.py method anchor not unique - upstream changed, review needed')
    method = '''
	def enumDevDvbFrontends(self):
		# Hi3798CV200: mainline DVB drivers (histb-dmx + mxl214) expose only
		# standard /dev/dvb/adapterN/frontend0 and no /proc/bus/nim_sockets
		# (dreambox-centric interface no mainline driver provides). Enumerate
		# frontends via FE_GET_INFO and return entries in the same format the
		# /proc parser produces. Returns None when the proc file exists so it
		# keeps priority.
		if exists("/proc/bus/nim_sockets"):
			return None
		if not exists("/dev/dvb"):
			return {}
		import ctypes
		import fcntl
		import os

		class FrontendInfo(ctypes.Structure):
			_fields_ = [
				("name", ctypes.c_char * 128),
				("type", ctypes.c_int),
				("frequency_min", ctypes.c_uint32),
				("frequency_max", ctypes.c_uint32),
				("frequency_stepsize", ctypes.c_uint32),
				("frequency_tolerance", ctypes.c_uint32),
				("symbol_rate_min", ctypes.c_uint32),
				("symbol_rate_max", ctypes.c_uint32),
				("symbol_rate_tolerance", ctypes.c_uint32),
				("notifier_delay", ctypes.c_uint32),
				("caps", ctypes.c_uint32),
			]

		FE_GET_INFO = 0x80A86F3D  # _IOR('o', 61, struct dvb_frontend_info)
		typeMap = {0: "DVB-S", 1: "DVB-C", 2: "DVB-T", 3: "ATSC"}
		entries = {}
		frontendIndex = 0
		for adapter in sorted(os.listdir("/dev/dvb")):
			if not adapter.startswith("adapter"):
				continue
			fePath = join("/dev/dvb", adapter, "frontend0")
			if not exists(fePath):
				continue
			try:
				fd = os.open(fePath, os.O_RDONLY)
				try:
					info = FrontendInfo()
					fcntl.ioctl(fd, FE_GET_INFO, info)
				finally:
					os.close(fd)
				feType = typeMap.get(info.type)
				if feType is None:
					print(f"[NimManager] {fePath}: unsupported FE type {info.type}, skipped")
					continue
				feName = info.name.decode("utf-8", "replace").strip() or fePath
				entries[frontendIndex] = {
					"type": feType,
					"name": feName,
					"isempty": False,
					"frontend_device": frontendIndex,
				}
				print(f"[NimManager] fallback NIM scan: slot {frontendIndex} '{feName}' ({feType})")
				frontendIndex += 1
			except Exception as err:
				print(f"[NimManager] fallback NIM scan failed on {fePath}: {err}")
		return entries

	def enumerateNIMs(self):
'''
    s = s.replace(anchor, method, 1)
    open(p, 'w').write(s)
print('NimManager.py /dev/dvb fallback NIM enumeration patched')

