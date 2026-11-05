"""Isolate absent vendor controls only after every backend and patch is installed.

Never synthesize capability files: native decoder/KMS/PCM provide real state.
Limit rewriting to C++ headers/sources and Python, as in the local workflow.
"""
from pathlib import Path

nfiles = 0
for directory in ('lib', 'main'):
    root = Path(directory)
    if not root.is_dir():
        raise SystemExit('missing source directory: ' + directory)
    for path in root.rglob('*'):
        if path.suffix not in ('.cpp', '.h', '.py') or not path.is_file():
            continue
        source = path.read_text(encoding='utf-8')
        if '/proc/stb' in source:
            path.write_text(source.replace('/proc/stb', '/var/stb'), encoding='utf-8')
            nfiles += 1
print('vendor procfs paths isolated in %d files' % nfiles)
