import io
import os
import sys
import tarfile
import zipfile
import hashlib

import pytest

# tools/ is not a package on sys.path by default; add it.
_TOOLS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "tools",
)
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

import ffmpeg_downloader as fd


@pytest.mark.unit
def test_verify_checksum_matches(tmp_path):
    p = tmp_path / "blob.bin"
    p.write_bytes(b"ffmpeg-bytes")
    digest = hashlib.sha256(b"ffmpeg-bytes").hexdigest()
    assert fd.verify_checksum(str(p), digest) is True


@pytest.mark.unit
def test_verify_checksum_rejects_one_bit_change(tmp_path):
    p = tmp_path / "blob.bin"
    p.write_bytes(b"ffmpeg-bytes")
    wrong = hashlib.sha256(b"ffmpeg-byteX").hexdigest()
    assert fd.verify_checksum(str(p), wrong) is False


@pytest.mark.unit
def test_is_within_directory_accepts_and_rejects(tmp_path):
    base = tmp_path / "dest"
    base.mkdir()
    assert fd._is_within_directory(str(base), str(base / "sub" / "f.bin")) is True
    assert fd._is_within_directory(str(base), str(tmp_path / "escape.bin")) is False


@pytest.mark.unit
def test_safe_extract_rejects_zip_traversal(tmp_path):
    archive = tmp_path / "evil.zip"
    with zipfile.ZipFile(str(archive), "w") as z:
        z.writestr("../evil.txt", "pwned")
    dest = tmp_path / "out"
    dest.mkdir()
    with pytest.raises(RuntimeError):
        fd.safe_extract(str(archive), str(dest))
    assert not (tmp_path / "evil.txt").exists()


@pytest.mark.unit
def test_safe_extract_rejects_tar_traversal(tmp_path):
    archive = tmp_path / "evil.tar"
    with tarfile.open(str(archive), "w") as t:
        data = b"pwned"
        info = tarfile.TarInfo(name="../evil.txt")
        info.size = len(data)
        t.addfile(info, io.BytesIO(data))
    dest = tmp_path / "out"
    dest.mkdir()
    with pytest.raises(RuntimeError):
        fd.safe_extract(str(archive), str(dest))
    assert not (tmp_path / "evil.txt").exists()


@pytest.mark.unit
def test_safe_extract_accepts_clean_zip(tmp_path):
    archive = tmp_path / "clean.zip"
    with zipfile.ZipFile(str(archive), "w") as z:
        z.writestr("bin/ffmpeg", "x")
    dest = tmp_path / "out"
    dest.mkdir()
    fd.safe_extract(str(archive), str(dest))
    assert (dest / "bin" / "ffmpeg").is_file()


@pytest.mark.unit
def test_main_aborts_on_checksum_mismatch(tmp_path, monkeypatch):
    # Build a real zip payload, but advertise a wrong checksum so main() aborts.
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as z:
        z.writestr("bin/ffmpeg", "x")
    raw = payload.getvalue()

    class _Resp(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): self.close()

    monkeypatch.setattr(fd.urllib.request, "urlopen",
                        lambda url, *a, **k: _Resp(raw))
    monkeypatch.setitem(
        fd.DOWNLOAD_SOURCES, ("Windows", "AMD64"),
        {"url": "https://example/ffmpeg.zip", "sha256": "00" * 32},
    )
    monkeypatch.setattr(fd, "detect_platform_arch", lambda: ("Windows", "AMD64"))

    with pytest.raises(SystemExit) as ei:
        fd.main(["--dest", str(tmp_path / "bin")])
    assert ei.value.code == 1
