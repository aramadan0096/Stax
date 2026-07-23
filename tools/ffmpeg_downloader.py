import argparse
import hashlib
import hmac
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

# Pinned, versioned artifacts (Windows + Linux only — no macOS, per SP program
# decision). Each record's sha256 MUST be populated from a human-approved,
# one-time download before this downloader is trusted in the field; until
# then verify_checksum() fails closed and main() aborts rather than
# installing an unverified binary.
DOWNLOAD_SOURCES = {
    ("Windows", "AMD64"): {
        "url": "https://www.gyan.dev/ffmpeg/builds/packages/ffmpeg-7.0.2-essentials_build.zip",
        "sha256": "",  # sha256 TODO(SP4/C3): populate via one-time human-approved download; empty => verify fails closed
    },
    ("Linux", "x86_64"): {
        "url": "https://johnvansickle.com/ffmpeg/old-releases/ffmpeg-7.0.2-amd64-static.tar.xz",
        "sha256": "",  # sha256 TODO(SP4/C3): populate via one-time human-approved download; empty => verify fails closed
    },
}


def verify_checksum(path, expected_sha256):
    """Return True iff the SHA-256 of `path` equals expected_sha256 (case-insensitive)."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return hmac.compare_digest(h.hexdigest(), (expected_sha256 or "").lower())


def _is_within_directory(directory, target):
    base = os.path.realpath(directory)
    resolved = os.path.realpath(os.path.join(base, target)) if not os.path.isabs(target) \
        else os.path.realpath(target)
    try:
        return os.path.commonpath([base, resolved]) == base
    except ValueError:
        return False


def safe_extract(archive, dest):
    """Extract a zip/tar into dest, rejecting any path-traversal member.

    Uses tarfile/zipfile data filters on Python >= 3.12; on older versions
    validates each member stays within dest before extracting. Raises
    RuntimeError on a traversing member or a corrupt archive.
    """
    print("Extracting:", archive)
    use_filter = sys.version_info >= (3, 12)
    if zipfile.is_zipfile(archive):
        try:
            with zipfile.ZipFile(archive, "r") as z:
                for name in z.namelist():
                    if not _is_within_directory(dest, name):
                        raise RuntimeError("Unsafe path in zip: {0}".format(name))
                z.extractall(dest)
        except zipfile.BadZipFile as exc:
            raise RuntimeError("Corrupt zip archive: {0}".format(exc))
        return True

    try:
        with tarfile.open(archive, "r:*") as t:
            for member in t.getmembers():
                if not _is_within_directory(dest, member.name):
                    raise RuntimeError("Unsafe path in tar: {0}".format(member.name))
            if use_filter:
                t.extractall(dest, filter="data")
            else:
                t.extractall(dest)
    except tarfile.TarError as exc:
        raise RuntimeError("Corrupt tar archive: {0}".format(exc))
    return True


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
    record = DOWNLOAD_SOURCES.get((sysname, arch))

    if not record:
        print("No download sources configured for this platform.")
        sys.exit(1)

    # Always download → even if already exists
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        archive = td / "ffmpeg_dl"

        url = record["url"]
        download(url, archive)

        if not verify_checksum(archive, record["sha256"]):
            print("SHA-256 mismatch for {0} — aborting (fail closed).".format(url))
            sys.exit(1)

        extracted = td / "extracted"
        extracted.mkdir()
        try:
            safe_extract(str(archive), str(extracted))
        except RuntimeError as exc:
            print("Extraction rejected:", exc)
            sys.exit(1)

        found = find_binaries(extracted)
        if not found:
            print("No ffmpeg binaries found inside the archive.")
            sys.exit(1)

        install_binaries(found, dest)

    print("\nDone.\nYour FFmpeg binaries are installed in:", dest)


if __name__ == "__main__":
    main()
