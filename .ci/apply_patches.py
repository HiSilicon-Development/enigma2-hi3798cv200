#!/usr/bin/env python3
"""Apply all .ci/patches/*.py (lexical order) against the enigma2 checkout.

Each patch script is a standalone python program executed with cwd=<checkout>.
Scripts must be idempotent (skip when already applied) and must raise
SystemExit when their anchor is missing - upstream drift means manual review,
never a silent skip.
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
