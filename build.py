import argparse
import ctypes
import hashlib
import json
import os
import shutil
import site
import struct
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
RESOURCE = ASSETS / "resource"
GUI_LOGO = ROOT / "docs" / "logo.png"
BUILD = ROOT / "build" / "agent"
DIST = ROOT / "dist"
DEFAULT_OUTPUT = DIST / "autodori"
MFA_VERSION = "v2.12.1"
MFA_ARCHIVE_URL = (
    "https://github.com/MaaXYZ/MFAAvalonia/releases/download/"
    f"{MFA_VERSION}/MFAAvalonia-{MFA_VERSION}-win-x64.zip"
)
MFA_ARCHIVE_SHA256 = "7b649c9e093f61567ae117b0825a62d912895c99ad59445c7fa37e6e5411e3bb"


def package_path(name: str) -> Path:
    for directory in site.getsitepackages():
        candidate = Path(directory) / name
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"Python package data directory not found: {name}")


def copy_project_files(project: Path) -> None:
    shutil.copy2(ASSETS / "interface.json", project / "interface.json")
    for language_file in ASSETS.glob("interface_*.json"):
        shutil.copy2(language_file, project / language_file.name)
    shutil.copytree(RESOURCE, project / "resource")
    if not GUI_LOGO.is_file():
        raise FileNotFoundError(f"GUI logo is missing: {GUI_LOGO}")
    icon_path = project / "Assets" / "logo.ico"
    icon_path.parent.mkdir()
    with Image.open(GUI_LOGO) as logo:
        logo.convert("RGBA").save(
            icon_path,
            format="ICO",
            sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)],
        )


def embed_windows_icon(executable: Path, icon: Path) -> None:
    if os.name != "nt":
        return

    icon_data = icon.read_bytes()
    reserved, icon_type, count = struct.unpack_from("<HHH", icon_data)
    if (reserved, icon_type) != (0, 1) or count == 0:
        raise ValueError(f"Invalid ICO file: {icon}")

    entries = []
    for index in range(count):
        width, height, colors, _, planes, bit_count, size, offset = struct.unpack_from(
            "<BBBBHHII", icon_data, 6 + index * 16
        )
        image = icon_data[offset : offset + size]
        if len(image) != size:
            raise ValueError(f"Invalid ICO image data: {icon}")
        entries.append((width, height, colors, planes, bit_count, image))

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.BeginUpdateResourceW.argtypes = [ctypes.c_wchar_p, ctypes.c_int]
    kernel32.BeginUpdateResourceW.restype = ctypes.c_void_p
    kernel32.UpdateResourceW.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_ushort,
        ctypes.c_void_p,
        ctypes.c_uint,
    ]
    kernel32.UpdateResourceW.restype = ctypes.c_int
    kernel32.EndUpdateResourceW.argtypes = [ctypes.c_void_p, ctypes.c_int]
    kernel32.EndUpdateResourceW.restype = ctypes.c_int

    handle = kernel32.BeginUpdateResourceW(str(executable), False)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())

    try:
        group = bytearray(struct.pack("<HHH", 0, 1, len(entries)))
        for resource_id, (width, height, colors, planes, bit_count, image) in enumerate(
            entries, 1
        ):
            image_buffer = ctypes.create_string_buffer(image)
            if not kernel32.UpdateResourceW(
                handle,
                ctypes.c_void_p(3),
                ctypes.c_void_p(resource_id),
                0,
                image_buffer,
                len(image),
            ):
                raise ctypes.WinError(ctypes.get_last_error())
            group.extend(
                struct.pack(
                    "<BBBBHHIH",
                    width,
                    height,
                    colors,
                    0,
                    planes,
                    bit_count,
                    len(image),
                    resource_id,
                )
            )

        group_buffer = ctypes.create_string_buffer(bytes(group))
        if not kernel32.UpdateResourceW(
            handle,
            ctypes.c_void_p(14),
            ctypes.c_void_p(1),
            0,
            group_buffer,
            len(group),
        ):
            raise ctypes.WinError(ctypes.get_last_error())
    except Exception:
        kernel32.EndUpdateResourceW(handle, True)
        raise

    if not kernel32.EndUpdateResourceW(handle, False):
        raise ctypes.WinError(ctypes.get_last_error())


def build_agent(project: Path, clean: bool) -> None:
    maa_bin = package_path("maa") / "bin"
    agent_binary = package_path("MaaAgentBinary")
    minitouch = ASSETS / "minitouch_EvATive7"
    if not minitouch.exists():
        raise FileNotFoundError("minitouch assets are missing")

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--onefile",
        "--name",
        "autodori-agent",
        "--distpath",
        str(BUILD / "dist"),
        "--workpath",
        str(BUILD / "work"),
        "--specpath",
        str(BUILD / "spec"),
        "--add-data",
        f"{maa_bin}{os.pathsep}maa/bin",
        "--add-data",
        f"{agent_binary}{os.pathsep}MaaAgentBinary",
        "--add-data",
        f"{minitouch}{os.pathsep}assets/minitouch_EvATive7",
        "--collect-all",
        "maa",
        "--collect-all",
        "MaaAgentBinary",
        str(ROOT / "src" / "agent.py"),
    ]
    if clean:
        command.insert(4, "--clean")
    subprocess.run(command, check=True)
    shutil.copy2(BUILD / "dist" / "autodori-agent.exe", project / "agent" / "autodori-agent.exe")


def download_mfa_archive(destination: Path) -> None:
    if destination.exists():
        with destination.open("rb") as archive:
            digest = hashlib.file_digest(archive, "sha256").hexdigest()
        if digest == MFA_ARCHIVE_SHA256:
            return
        destination.unlink()

    request = urllib.request.Request(MFA_ARCHIVE_URL, headers={"User-Agent": "autodori-build"})
    with urllib.request.urlopen(request) as response, destination.open("wb") as output:
        shutil.copyfileobj(response, output)

    with destination.open("rb") as archive:
        digest = hashlib.file_digest(archive, "sha256").hexdigest()
    if digest != MFA_ARCHIVE_SHA256:
        raise RuntimeError(f"MFAAvalonia archive checksum mismatch: {digest}")


def extract_mfa_archive(archive: Path, destination: Path) -> None:
    with zipfile.ZipFile(archive) as bundle:
        destination_root = destination.resolve()
        for member in bundle.infolist():
            member_path = (destination_root / member.filename).resolve()
            if not member_path.is_relative_to(destination_root):
                raise RuntimeError(f"MFAAvalonia archive has an invalid member: {member.filename}")
        bundle.extractall(destination)


def publish_gui(project: Path, output: Path) -> None:
    archive = BUILD / f"MFAAvalonia-{MFA_VERSION}-win-x64.zip"
    download_mfa_archive(archive)
    extract_mfa_archive(archive, output)
    launcher = output / "MFAAvalonia.exe"
    if not launcher.is_file():
        raise FileNotFoundError(f"MFAAvalonia launcher is missing: {launcher}")
    launcher = launcher.rename(output / "autodori.exe")
    embed_windows_icon(launcher, project / "Assets" / "logo.ico")
    shutil.copytree(project, output, dirs_exist_ok=True)


def project_version() -> str:
    with (ASSETS / "interface.json").open(encoding="utf-8") as interface_file:
        version = json.load(interface_file).get("version")
    if not isinstance(version, str) or not version:
        raise RuntimeError("assets/interface.json must define a non-empty version")
    return version


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the autodori MFA package")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--without-gui", action="store_true")
    parser.add_argument("--clean", action="store_true", help="discard build caches before building")
    parser.add_argument("--version", default=project_version())
    parser.add_argument("--arch", default="win-x64")
    args = parser.parse_args()

    output = args.output.resolve()
    if args.clean and BUILD.exists():
        shutil.rmtree(BUILD)
    project = BUILD / "project"
    if project.exists():
        shutil.rmtree(project)
    project.mkdir(parents=True)
    (project / "agent").mkdir()

    copy_project_files(project)
    build_agent(project, args.clean)

    if output.exists():
        shutil.rmtree(output)
    if args.without_gui:
        shutil.copytree(project, output)
    else:
        publish_gui(project, output)

    archive_name = f"autodori-{args.version}-{args.arch}"
    archive = Path(
        shutil.make_archive(
            str(output.parent / archive_name),
            "zip",
            root_dir=output.parent,
            base_dir=output.name,
        )
    )
    print(f"MFA project package created: {output}")
    print(f"MFA project archive created: {archive}")


if __name__ == "__main__":
    main()
