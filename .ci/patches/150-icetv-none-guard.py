# ---- IceTV gotRecordEvent None 防御（2026-10-30 盒子实测）----
# Navigation.py streamStatusChangedCB() 以 x(None, evStart/evEnd)
# 通知流媒体起停，IceTV 插件直接 rec_service.getPtrString() →
# AttributeError: 'NoneType' object has no attribute
# 'getPtrString'，每次 web 流起停刷 traceback（上游 bug）。
p = 'lib/python/Plugins/SystemPlugins/IceTV/plugin.py'
s = open(p).read()
old = ('        if event not in self.START_EVENTS and event not in self.END_EVENTS and event not in self.ERROR_EVENTS:\n'
       '            return\n'
       '\n'
       '        rec_service_id = rec_service.getPtrString()\n')
new = ('        if event not in self.START_EVENTS and event not in self.END_EVENTS and event not in self.ERROR_EVENTS:\n'
       '            return\n'
       '\n'
       '        if rec_service is None:\n'
       '            # Navigation.streamStatusChangedCB() fires record_event with a\n'
       '            # NULL service for streaming start/stop. Not a recording job:\n'
       '            # there is nothing to look up, so just ignore the event.\n'
       '            return\n'
       '\n'
       '        rec_service_id = rec_service.getPtrString()\n')
if old in s:
    s = s.replace(old, new, 1)
elif 'rec_service is None' in s:
    pass
else:
    raise SystemExit('IceTV plugin.py gotRecordEvent anchor not found - upstream changed, review needed')
open(p, 'w').write(s)
print('IceTV plugin.py gotRecordEvent None-guard patched')

