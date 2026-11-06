#!/usr/bin/env python3
"""Apply the maintained HiSTB OpenWebif patch to its complete source tree.

Usage: python3 packaging/apply-openwebif.py PATH_TO_OPENWEBIF_SOURCE
Observed upstream reference: oe-alliance/OpenWebif main
7a7bb63ba166ccf6623706eba019584231840a6d (2026-11-06), not a fetch-policy pin.
Run after fetching upstream source, before rebuilding desktop/mobile assets.
This does not edit device authentication, user settings or skins.
The separate histb-screenshot.cpp helper is built for the target, not executed
by this script. It requires the matching Enigma2 native-frame lease service.
"""
from pathlib import Path
import subprocess
import sys

SOURCE_COMMIT = "7a7bb63ba166ccf6623706eba019584231840a6d"


def main():
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    target = Path(sys.argv[1]).resolve()
    if not (target / "plugin/controllers/models/grab.py").is_file() or not (target / "sourcefiles/package.json").is_file():
        raise SystemExit(f"Not a complete OpenWebif source tree: {target}")
    patch = Path(__file__).resolve().with_name("openwebif-histb.patch")
    command = ["patch", "--batch", "--silent", "-p1", "--directory", str(target), "--input", str(patch)]
    reverse = subprocess.run(command + ["--dry-run", "--reverse", "--force"], capture_output=True)
    if reverse.returncode == 0:
        print(f"OpenWebif HiSTB adaptation already applied (base {SOURCE_COMMIT})")
        return
    subprocess.run(command + ["--dry-run", "--forward"], check=True)
    subprocess.run(command + ["--forward", "--no-backup-if-mismatch"], check=True)
    print(f"Applied OpenWebif HiSTB adaptation (base {SOURCE_COMMIT})")


if __name__ == "__main__":
    main()
