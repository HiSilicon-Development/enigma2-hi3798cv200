"""Apply reviewed source patches after native backend wiring, before isolation.

Use a fresh official checkout for the complete preparation pipeline: patches
are ordered transformations and later patches may replace earlier hunks.
An applicability failure is upstream drift and must stop preparation.
"""
from pathlib import Path
import subprocess

patches = sorted((Path(__file__).resolve().parents[2] / 'packaging' / 'patches').glob('*.patch'))
if not patches:
    raise SystemExit('no maintained source patches found in packaging/patches/')
for patch in patches:
    print('==> maintained source patch: ' + patch.name, flush=True)
    subprocess.run(['git', 'apply', '--check', str(patch)], check=True)
    subprocess.run(['git', 'apply', str(patch)], check=True)
