#!/usr/bin/env python3
"""Construct runtime-only Debian packages without touching the target system.

E2VER is required. Usage:
  package-runtime.py library libdvbsi++ STAGING 'libdvbsi++.so.*'
  package-runtime.py library libtuxtxt STAGING 'libtuxtxt.so.*' 'libtuxtxt32bpp.so.*'
  package-runtime.py enigma2 STAGING

Defaults match enigma2.yml. Override DVBSI_STAGING and TUXTXT_STAGING for local
builds. DPKG_SHLIBDEPS and READELF may select cross/sysroot-aware commands;
dependencies must be resolved against the same Debian release as the build.
Cross builds require DPKG_ADMINDIR pointing at an isolated target database and
SYSTEM_SHLIBS containing the target's genuine concatenated dpkg .shlibs files.
Supply target library search paths in DPKG_SHLIBDEPS and set DEB_HOST_ARCH=arm64.
The Enigma2 input needs the supervisor, socketdaemon, plugins, skins, locales,
postinst and e2.service already staged as in the workflow. Either /etc/enigma2
or the previous /usr/local/etc/enigma2 layout is accepted and seeded safely.
"""

import fnmatch
from hashlib import md5
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile


WORKSPACE = Path(os.environ.get("GITHUB_WORKSPACE", Path(__file__).resolve().parents[1]))
VERSION = os.environ["E2VER"]
ARCH = os.environ.get("DEB_HOST_ARCH", "arm64")
MAIN_PACKAGE = "enigma2-hi3798cv200"
LOCAL_LIBRARIES = {
    "libdvbsi++": Path(os.environ.get("DVBSI_STAGING", WORKSPACE / ".pkg-libdvbsi")),
    "libtuxtxt": Path(os.environ.get("TUXTXT_STAGING", WORKSPACE / ".pkg-libtuxtxt")),
}


def elf(path):
    if path.is_symlink() or not path.is_file():
        return False
    with path.open("rb") as stream:
        return stream.read(4) == b"\x7fELF"


def elf_files(root):
    return [path for path in root.rglob("*") if elf(path)]


def shlibs(root, package):
    result = set()
    for path in elf_files(root):
        dynamic = subprocess.check_output(
            [*shlex.split(os.environ.get("READELF", "readelf")), "-d", str(path)], text=True
        )
        # Private Python modules can have an unversioned SONAME (socketmmi.so).
        # They still need dependency scanning, but export no Debian shlibs ABI.
        match = re.search(r"\(SONAME\).*\[([^\]]+)\.so\.([^\]]+)\]", dynamic)
        if match:
            name, abi = match.groups()
            result.add(f"{name} {abi} {package} (= {VERSION})")
    return sorted(result)


def dependencies(root, package):
    native_arch = subprocess.check_output(["dpkg", "--print-architecture"], text=True).strip()
    system_shlibs = os.environ.get("SYSTEM_SHLIBS")
    if native_arch != ARCH and (not os.environ.get("DPKG_ADMINDIR") or not system_shlibs):
        raise SystemExit("Cross packaging requires isolated DPKG_ADMINDIR and target SYSTEM_SHLIBS; refusing host dependency metadata")
    binaries = elf_files(root)
    if not binaries:
        raise SystemExit(f"Refusing empty runtime package: {package}")
    maps = set(shlibs(root, package))
    directories = {path.parent for path in binaries}
    for local_package, staging in LOCAL_LIBRARIES.items():
        if not staging.is_dir():
            raise SystemExit(f"Missing runtime staging: {staging}")
        maps.update(shlibs(staging, local_package))
        directories.update(path.parent for path in elf_files(staging))
    with tempfile.TemporaryDirectory(prefix="e2-shlibdeps-") as temp:
        debian = Path(temp) / "debian"
        debian.mkdir()
        (debian / "control").write_text(
            f"Source: enigma2-port\n\nPackage: {package}\nArchitecture: any\nDescription: Enigma2 runtime\n"
        )
        (debian / "shlibs.local").write_text("\n".join(sorted(maps)) + "\n")
        if system_shlibs:
            with (debian / "shlibs.local").open("a") as stream:
                stream.write(Path(system_shlibs).read_text().rstrip("\n") + "\n")
        command = shlex.split(os.environ.get("DPKG_SHLIBDEPS", "dpkg-shlibdeps"))
        if os.environ.get("DPKG_ADMINDIR"):
            command.append(f"--admindir={os.environ['DPKG_ADMINDIR']}")
        command += ["-O", f"-x{package}"]
        command += [f"-l{directory}" for directory in sorted(directories)]
        command += [f"-e{binary}" for binary in binaries]
        output = subprocess.check_output(command, cwd=temp, text=True, env={**os.environ, "DEB_HOST_ARCH": ARCH})
    return next(line.partition("=")[2] for line in output.splitlines() if line.startswith("shlibs:Depends="))


def build(root, package, description, extra=()):
    control = root / "DEBIAN"
    control.mkdir(exist_ok=True)
    deps = dependencies(root, package)
    depends = ", ".join([item for item in (deps, *extra) if item])
    (control / "control").write_text(
        f"Package: {package}\nVersion: {VERSION}\nArchitecture: {ARCH}\n"
        "Maintainer: manhere <manhere@gmail.com>\n"
        f"Depends: {depends}\nSection: {'video' if package == MAIN_PACKAGE else 'libs'}\n"
        f"Priority: optional\nDescription: {description}\n"
        " Built for Debian arm64; shared-library dependencies are derived from ELF metadata.\n"
    )
    metadata = shlibs(root, package)
    if metadata:
        (control / "shlibs").write_text("\n".join(metadata) + "\n")
        (control / "triggers").write_text("activate-noawait ldconfig\n")
    output = WORKSPACE / f"{package}_{VERSION}_{ARCH}.deb"
    subprocess.run(["dpkg-deb", "--build", "--root-owner-group", str(root), str(output)], check=True)


def library(package, staging, patterns):
    if package not in LOCAL_LIBRARIES or not patterns:
        raise SystemExit(__doc__)
    for pattern in patterns:
        if not any(elf(path) for path in staging.rglob(pattern)):
            raise SystemExit(f"Missing ELF runtime payload {pattern} in {staging}")
    with tempfile.TemporaryDirectory(prefix="e2-runtime-") as temp:
        root = Path(temp)
        for source in staging.rglob("*"):
            if (source.is_file() or source.is_symlink()) and fnmatch.fnmatch(source.name, "*.so*"):
                target = root / source.relative_to(staging)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target, follow_symlinks=False)
        for link in root.rglob("*"):
            if link.is_symlink() and not link.resolve().is_file():
                raise SystemExit(f"Broken runtime library link: {link}")
        build(root, package, "DVB SI library runtime" if package == "libdvbsi++" else "Teletext and 32bpp renderer runtime")


def machine_identity(root):
    path = root / "usr/local/lib/enigma.info"
    source = path if path.is_file() else Path(__file__).with_name("enigma.info")
    # This is an application port, not an OE firmware image. In particular,
    # never advertise partitions or image files which an updater might flash.
    updates = {
        "displaybrand": "HiSilicon", "displaymodel": "Hi3798CV200",
        "displaydistro": "Debian / OpenATV", "distro": "debian",
        "platform": "hi3798cv200", "friendlyfamily": "hi3798cv200",
        "machinebuild": os.environ.get("MACHINEBUILD", "u5"),
        "model": os.environ.get("BOXTYPE", "u5"),
        "feedsurl": "", "imagedir": "", "kernel": "", "kernelfile": "",
        "mtdblack": "", "mtdbootfs": "", "mtdkernel": "", "mtdrootfs": "",
        "rootfile": "", "oe": "",
    }
    lines = []
    for line in source.read_text().splitlines():
        key = line.partition("=")[0]
        if key == "checksum":
            continue
        lines.append(f"{key}={updates[key]!r}" if key in updates else line)
    # BoxInformation.checkChecksum hashes all non-checksum lines plus a newline.
    payload = "\n".join(lines) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload + f"checksum={md5(payload.encode('utf-8')).hexdigest()}\n")


def enigma2(root):
    for firmware in ("lib/firmware/hisilicon", "usr/lib/firmware/hisilicon"):
        if (root / firmware).exists():
            raise SystemExit(f"Kernel-owned firmware must not be packaged: {firmware}")
    for required in ("usr/local/bin/enigma2.bin", "usr/local/bin/enigma2", "usr/local/bin/socketdaemon", "DEBIAN/postinst"):
        if not (root / required).is_file():
            raise SystemExit(f"Missing Enigma2 runtime file: {required}")
    if not elf(root / "usr/local/bin/enigma2.bin"):
        raise SystemExit("enigma2.bin must contain the real ELF executable")
    # MetrixHD uses OE's absolute font paths; autotools installs the same
    # supplied fonts under this application's /usr/local prefix on Debian.
    for name in ("lcd.ttf", "ae_AlMateen.ttf", "andale.ttf", "nmsbd.ttf", "DejaVuSans.ttf"):
        source = root / "usr/local/share/fonts" / name
        if not source.is_file():
            raise SystemExit(f"Missing skin font: {name}")
        target = root / "usr/share/fonts" / name
        if not target.exists() and not target.is_symlink():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.symlink_to(os.path.relpath(source, target.parent))
    # Configuration is installed as immutable defaults then copied only if absent.
    # This also preserves unowned settings on the very first dpkg installation.
    defaults = root / "usr/local/share/enigma2/defaults/enigma2"
    defaults.mkdir(parents=True, exist_ok=True)
    for source_dir in (root / "etc/enigma2", root / "usr/local/etc/enigma2"):
        if source_dir.is_dir() and not source_dir.is_symlink():
            shutil.copytree(source_dir, defaults, dirs_exist_ok=True)
            shutil.rmtree(source_dir)
    machine_identity(root)
    (root / "DEBIAN/conffiles").write_text("".join(
        f"/{path.relative_to(root)}\n"
        for path in sorted((root / "etc").rglob("*")) if path.is_file() and not path.is_symlink()
    ))
    extra = [
        "gstreamer1.0-plugins-base", "gstreamer1.0-plugins-good", "gstreamer1.0-plugins-bad",
        "gstreamer1.0-libav", "libusb-1.0-0", "init-system-helpers", "udev",
        f"libdvbsi++ (= {VERSION})", f"libtuxtxt (= {VERSION})",
    ]
    if not (root / "usr/local/lib/libpython3.13.so.1.0").exists():
        extra += [
            "python3 (>= 3.13)", "python3 (<< 3.14)", "libpython3.13", "python3-twisted",
            "python3-openssl", "python3-service-identity", "python3-idna", "python3-usb",
            "python3-cheetah", "python3-pil", "python3-requests",
        ]
    build(root, MAIN_PACKAGE, "OpenATV Enigma2 for HiSilicon Hi3798CV200", extra)


def main():
    if len(sys.argv) >= 5 and sys.argv[1] == "library":
        library(sys.argv[2], Path(sys.argv[3]).resolve(), sys.argv[4:])
    elif len(sys.argv) == 3 and sys.argv[1] == "enigma2":
        enigma2(Path(sys.argv[2]).resolve())
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
