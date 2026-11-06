#!/usr/bin/env python3
"""Prepare an official Enigma2 checkout using .ci/patches/*.py in lexical order.

010-150: Debian compatibility and shared native-KMS display installation.
200: HiSTB decoder wiring and all companion headers.
210: reject zero-frequency channel updates and omit them from both DB formats.
220: apply packaging/patches/*.patch in lexical order.
300: isolate unavailable vendor procfs paths, including newly installed sources.

Each script runs with cwd=<checkout>. Use a fresh official checkout for this
complete ordered transformation; overlapping maintained patches are not a
repeatable overlay. Missing anchors and failed patches stop on upstream drift.
"""
import glob
import os
import subprocess
import sys

checkout = sys.argv[1] if len(sys.argv) > 1 else 'enigma2'
here = os.path.dirname(os.path.abspath(__file__))
patches = sorted(glob.glob(os.path.join(here, 'patches', '*.py')))
if not patches:
    sys.exit('no patch scripts found in .ci/patches/')
for p in patches:
    print('==> %s' % os.path.basename(p), flush=True)
    r = subprocess.run([sys.executable, p], cwd=checkout)
    if r.returncode != 0:
        sys.exit('patch failed: %s (exit %d)' % (p, r.returncode))
print('all %d patches applied' % len(patches))
