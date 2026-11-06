"""Apply reviewed source patches after native backend wiring, before isolation.

Use a fresh official checkout for the complete preparation pipeline: patches
are ordered transformations and later patches may replace earlier hunks, so
neither forward nor reverse applicability can be tested patch-by-patch after
the chain has run.  A stamp file records that the chain completed, which keeps
re-running the harness a no-op; a fresh CI checkout has no stamp and runs it.
An applicability failure is upstream drift and must stop preparation.
"""
from pathlib import Path
import subprocess

patches = sorted((Path(__file__).resolve().parents[2] / 'packaging' / 'patches').glob('*.patch'))
if not patches:
    raise SystemExit('no maintained source patches found in packaging/patches/')

stamp = Path('.ci-source-patches.stamp')
if stamp.is_file():
    print('==> maintained source patches already applied (%s)' % stamp)
else:
    for patch in patches:
        print('==> maintained source patch: ' + patch.name, flush=True)
        subprocess.run(['git', 'apply', '--check', str(patch)], check=True)
        subprocess.run(['git', 'apply', str(patch)], check=True)
    stamp.write_text(''.join(p.name + '\n' for p in patches))
