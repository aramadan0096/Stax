import argparse
import os
import platform
import shutil
import stat
import sys
import tempfile
import urllib.request
import zipfile
import tarfile
from pathlib import Path

BIN_NAMES = ["ffmpeg", "ffplay", "ffprobe"]

DOWNLOAD_SOURCES = {
    ("Windows", "AMD64"): [
        "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip",
    ],
    ("Linux", "x86_64"): [
        "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz",
    ],
    ("Darwin", "arm64"): [
        "https://evermeet.cx/ffmpeg/ffmpeg.zip",
    ],
    ("Darwin", "x86_64"): [
        "https://evermeet.cx/ffmpeg/ffmpeg.zip",
    ],
}


def detect_platform_arch():
    sysname = platform.system()
    machine = platform.machine().lower()
    if machine in ("amd64", "x86_64", "x64"):
        arch = "AMD64" if sysname == "Windows" else "x86_64"
    elif machine in ("aarch64", "arm64"):
        arch = "arm64"
    else:
        arch = machine
    return sysname, arch


def download(url, outpath):
    print(f"Downloading: {url}")
    with urllib.request.urlopen(url) as r, open(outpath, "wb") as f:
        shutil.copyfileobj(r, f)
    print("Download complete:", outpath)


def extract(archive, dest):
    print("Extracting:", archive)
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive, "r") as z:
            z.extractall(dest)
        return True

    try:
        with tarfile.open(archive, "r:*") as t:
            t.extractall(dest)
        return True
    except:
        return False


def find_binaries(folder):
    found = {}
    for root, _, files in os.walk(folder):
        for f in files:
            name = f.lower()
            for bin_name in BIN_NAMES:
                if name.startswith(bin_name):
                    found[bin_name] = os.path.join(root, f)
    return found


def install_binaries(found, dest):
    dest.mkdir(parents=True, exist_ok=True)

    for name, src in found.items():
        exe = name + (".exe" if platform.system() == "Windows" else "")
        dst = dest / exe
        shutil.copy2(src, dst)
        if platform.system() != "Windows":
            dst.chmod(0o755)
        print(f"Installed {name} → {dst}")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Download FFmpeg binaries into the project.")
    parser.add_argument(
        "--dest",
        type=str,
        default="bin",
        help="Destination directory for FFmpeg binaries (default: bin)",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    dest = Path(args.dest).resolve()
    dest.mkdir(parents=True, exist_ok=True)
    print("Installing FFmpeg into:", dest)

    sysname, arch = detect_platform_arch()
    urls = DOWNLOAD_SOURCES.get((sysname, arch))

    if not urls:
        print("No download sources configured for this platform.")
        sys.exit(1)

    # Always download → even if already exists
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        archive = td / "ffmpeg_dl"

        # Use first working URL
        url = urls[0]
        download(url, archive)

        extracted = td / "extracted"
        extracted.mkdir()

        ok = extract(archive, extracted)
        if not ok:
            print("Extraction failed.")
            sys.exit(1)

        found = find_binaries(extracted)
        if not found:
            print("No ffmpeg binaries found inside the archive.")
            sys.exit(1)

        install_binaries(found, dest)

    print("\nDone.\nYour FFmpeg binaries are installed in:", dest)


if __name__ == "__main__":
    main()
