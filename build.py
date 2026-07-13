import argparse
import hashlib
import os
import shutil
import site
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
RESOURCE = ASSETS / "resource"
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
    shutil.copytree(RESOURCE, project / "resource")


def build_agent(project: Path) -> None:
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
        "--clean",
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
        str(ROOT / "src" / "autodori.py"),
    ]
    subprocess.run(command, check=True)
    shutil.copy2(BUILD / "dist" / "autodori-agent.exe", project / "agent" / "autodori-agent.exe")


def download_mfa_archive(destination: Path) -> None:
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
    shutil.copytree(project, output, dirs_exist_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the autodori MFA package")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--without-gui", action="store_true")
    args = parser.parse_args()

    output = args.output.resolve()
    project = BUILD / "project"
    if BUILD.exists():
        shutil.rmtree(BUILD)
    project.mkdir(parents=True)
    (project / "agent").mkdir()

    copy_project_files(project)
    build_agent(project)

    if output.exists():
        shutil.rmtree(output)
    if args.without_gui:
        shutil.copytree(project, output)
    else:
        publish_gui(project, output)

    print(f"MFA project package created: {output}")


if __name__ == "__main__":
    main()
