#!/usr/bin/env python3
"""Fetch CI sources and retain resolved commits in sources.lock.json.

Usage: fetch-source.py clone NAME DEST
       fetch-source.py file NAME REPOSITORY_PATH DEST
SOURCE_REFS is a JSON object mapping the names below to branches, tags or full
commit IDs. Passing a previous run's sources.lock.json pins every repository.
This records source identity, not a lock of apt packages or Python wheels.
"""

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import urllib.parse
import urllib.request


SOURCES = {
    "enigma2": ("openatv/enigma2", "a6db04f56fd3314f9c3c30df639a4a394b6332c1"),
    "libdvbsi": ("OpenVisionE2/libdvbsi", "HEAD"),
    "tuxtxt": ("oe-alliance/tuxtxt", "HEAD"),
    "tuxbox-headers": ("OpenPLi/OpenPLi-1", "master"),
    "kernel-headers": ("HiSilicon-Development/linux-6.12.y", "main"),
    "hivxe-ffmpeg": ("HiSilicon-Development/FFmpeg", "HEAD"),
    "socketdaemon": ("openatv/socketdaemon", "HEAD"),
    "skindefault": ("openatv/oe-alliance-e2-skindefault", "HEAD"),
    "tuxbox-common": ("oe-alliance/oe-alliance-tuxbox-common", "HEAD"),
    "weatherinfo": ("openatv/WeatherInfo", "HEAD"),
    "oe-alliance-core": ("oe-alliance/oe-alliance-core", "master"),
    "metrixhd": ("openatv/MetrixHD", "HEAD"),
    "openwebif": ("oe-alliance/OpenWebif", "b511d277098de5e0f0a16a2cd4e55510874e19df"),
}


def git(*args):
    return subprocess.check_output(["git", *args], text=True).strip()


def main():
    action, name, *args = sys.argv[1:]
    repository, default = SOURCES[name]
    refs = json.loads(os.environ.get("SOURCE_REFS", "{}"))
    if not isinstance(refs, dict) or refs.keys() - SOURCES.keys():
        raise SystemExit("SOURCE_REFS must map known source names to refs")
    ref = refs.get(name, default)
    if not isinstance(ref, str) or not ref:
        raise SystemExit(f"Invalid source ref for {name}")
    workspace = Path(os.environ.get("GITHUB_WORKSPACE", Path(__file__).resolve().parents[1]))
    lock_path = workspace / "sources.lock.json"
    lock = json.loads(lock_path.read_text()) if lock_path.exists() else {}
    url = f"https://github.com/{repository}.git"
    sha = lock.get(name)
    if sha is None:
        if re.fullmatch(r"[0-9a-fA-F]{40}", ref):
            sha = ref.lower()
        else:
            selectors = [ref] if ref == "HEAD" or ref.startswith("refs/") else [
                f"refs/heads/{ref}", f"refs/tags/{ref}", f"refs/tags/{ref}^{{}}"
            ]
            rows = [line.split() for line in git("ls-remote", url, *selectors).splitlines()]
            peeled = [commit for commit, label in rows if label.endswith("^{}")]
            commits = set(peeled or [commit for commit, _ in rows])
            if len(commits) != 1:
                raise SystemExit(f"Source ref must resolve unambiguously: {name}={ref}")
            sha = commits.pop()
    if action == "clone" and len(args) == 1:
        destination = str(Path(args[0]).resolve())
        git("init", destination)
        git("-C", destination, "remote", "add", "origin", url)
        git("-C", destination, "fetch", "--depth=1", "origin", sha)
        git("-C", destination, "checkout", "--detach", "FETCH_HEAD")
        if git("-C", destination, "rev-parse", "HEAD") != sha:
            raise SystemExit(f"Unexpected checked-out source for {name}")
    elif action == "file" and len(args) == 2:
        source, destination = args
        source = urllib.parse.quote(source, safe="/")
        with urllib.request.urlopen(f"https://raw.githubusercontent.com/{repository}/{sha}/{source}") as response:
            Path(destination).write_bytes(response.read())
    else:
        raise SystemExit(__doc__)
    lock[name] = sha
    lock_path.write_text(json.dumps(lock, sort_keys=True, indent=2) + "\n")
    print(f"{name}: {sha}")


if __name__ == "__main__":
    main()
