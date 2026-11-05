#!/usr/bin/env python3
"""Apply the maintained HiSTB OpenWebif patch to source or an installed plugin.

Usage: python3 packaging/apply-openwebif.py PATH_TO_OPENWEBIF_OR_PLUGIN
Upstream base: oe-alliance/OpenWebif b511d277098de5e0f0a16a2cd4e55510874e19df.
Run after fetching the pinned source, before packaging. This does not change
OpenWebif authentication, Enigma2 settings, skins or the public asset bundles.
The separate histb-screenshot.cpp helper is built for the target, not executed
by this script. It requires the matching Enigma2 native-frame lease service.
"""
from pathlib import Path
import subprocess
import sys

SOURCE_COMMIT = "b511d277098de5e0f0a16a2cd4e55510874e19df"


def main():
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    target = Path(sys.argv[1]).resolve()
    if (target / "plugin/controllers/models/grab.py").is_file():
        target = target / "plugin"
    if not (target / "controllers/models/grab.py").is_file():
        raise SystemExit(f"Not an OpenWebif plugin tree: {target}")
    patch = Path(__file__).resolve().with_name("openwebif-histb.patch")
    command = ["patch", "--batch", "--silent", "-p2", "--directory", str(target), "--input", str(patch)]
    reverse = subprocess.run(command + ["--dry-run", "--reverse", "--force"], capture_output=True)
    if reverse.returncode == 0:
        print(f"OpenWebif HiSTB adaptation already applied (base {SOURCE_COMMIT})")
        return
    subprocess.run(command + ["--dry-run", "--forward"], check=True)
    subprocess.run(command + ["--forward", "--no-backup-if-mismatch"], check=True)
    print(f"Applied OpenWebif HiSTB adaptation (base {SOURCE_COMMIT})")


if __name__ == "__main__":
    main()
