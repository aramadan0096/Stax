# SP4 — Security Hardening — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the six SP4 security issues (C2, C3, H2, H6, M2, L9) by routing every dangerous sink through a small, pure, unit-tested validation function, then rewiring the callers. All tests are pure-logic (`tmp_path`/`monkeypatch`, mocked `urlopen`); no network, no real Nuke, headless Qt only.

**Architecture:** Each fix adds a module-level validator (`resolve_trusted_script`, `verify_checksum`/`safe_extract`, `hash_password`/`verify_password`, `register_model`/`_is_within`, `path_within_roots`, `resolve_token`) and confines the sink to it. Fail-closed defaults: no trusted dir ⇒ hooks off; empty ingest roots ⇒ API ingest off; empty token ⇒ 401; unregistered model ⇒ 403.

**Tech Stack:** Python 3.9 (stdlib `hashlib`/`hmac`/`secrets`/`os.path`), Flask (API tests), PySide2 (offscreen), pytest, GitHub Actions, uv. **No new runtime dependency.**

## Global Constraints

- **Platforms:** Windows + Linux only. CI matrix = `windows-latest`, `ubuntu-latest`.
- **Python:** 3.9 floor; extraction fallback covers 3.9–3.11, `filter="data"` used on ≥3.12.
- **No new dependency.** H2 uses stdlib `hashlib.pbkdf2_hmac`, not bcrypt/argon2.
- **Fail closed.** Every new default (`trusted_processors_dir=None`, `api_ingest_roots=[]`, empty token) denies access.
- **Locked scopes:** C2 restricts *where* scripts load — it does **not** sandbox `exec`. L9 makes the *client* HTTPS-capable — the API server stays localhost HTTP. Do not expand beyond the six issues.
- **Import convention:** `src/` is on `sys.path`; import flat (`from db_manager import ...`, `from extensibility_hooks import ...`). Tools import from `tools/` by path.
- **TDD:** write the failing test first, watch it fail, implement, watch it pass, commit (conventional prefixes: `fix:`, `test:`, `build:`).
- **No product bug outside SP4 scope.** If a test reveals an unrelated defect, note it — do not fix it here.

---

## Key signatures (verified against the codebase)

- `Config(config_path='./config/config.json')`; `.get(key, default=None)`, `.set(key, value)` (saves), `.get_all()`; `DEFAULT_CONFIG` dict at `src/config.py:16`. Existing keys: `previews_path`, `default_copy_policy`, `pre_ingest_processor`/`post_ingest_processor`/`post_import_processor`.
- `ProcessorHook.__init__(self, script_path=None)`; `.execute(context)`; `.enabled` bool (`src/extensibility_hooks.py:13,16,26`). `ProcessorManager.__init__(self, config)` where `config` is a **dict** (`main.py:97` passes `self.config.get_all()`); builds `PreIngestHook`/`PostIngestHook`/`PostImportHook`; `reload_hooks()` at `:199`.
- `DatabaseManager(db_path, enable_logging=False, use_file_lock=True)`; `.get_connection()` context manager; `create_user(username, password, role='user', email=None)` (`:1490`); `authenticate_user(username, password)` (`:1520`); `change_user_password(user_id, new_password)` (`:1627`); `get_user_by_username(username)` (`:1570`). Live `users` table columns: `user_id, username, password_hash, role, email, is_active, created_at, last_login` (`src/db_manager.py:296`). Default admin inserted at `:350-354` (schema) and `:425-430` (Migration 3).
- `tools/ffmpeg_downloader.py`: `DOWNLOAD_SOURCES` dict (`:15`), `download(url, outpath)` (`:43`), `extract(archive, dest)` (`:50`, bare `except`), `main(argv=None)` (`:99`). Uses `urllib.request`, `zipfile`, `tarfile`.
- `src/geometry_viewer.py`: `_norm(path)` (`:48`), `_make_handler(viewer_dir, dependencies_root, project_root)` (`:64`), `GeometryViewerServer.__init__(self, project_root)` (`:159`), `.instance(project_root)` classmethod (`:172`), `.model_endpoint(model_path)` (`:182`), `.viewer_url_for_model(model_path)` (`:192`), `GeometryViewerWidget.__init__(self, project_root, parent=None)` (`:204`), `.load_geometry(glb_path)` (`:274`). `/model/` handler at `:96-143`; `translate_path` at `:75-90`.
- `src/api_server.py`: `_build_flask_app(db, config)` (`:76`), `require_auth` wrapper (`:86`, `provided != token`), `ingest` route (`:152`), `_SimpleHandler.__call__` (`:213`, `token != ...`).
- `tools/stax_cli.py`: `_base(host, port)` (`:124`), `_request(method, url, token, payload=None)` (`:81`), `_build_parser()` (`:303`, `--token` default `os.environ.get("STAX_API_TOKEN","")`), `main()` (`:398`).
- SP0 fixtures (from `tests/conftest.py`): `stax_db` (real `DatabaseManager` on a `tmp_path` DB, `use_file_lock=False`), `stax_config`, `tmp_path`, `monkeypatch`.

---

## Task 1: C2 — Confine processor `exec()` to a trusted directory

**Files:**
- Modify: `src/extensibility_hooks.py`, `src/config.py`
- Create: `tests/unit/test_hook_path_validation.py`

**Interfaces:**
- Produces: `resolve_trusted_script(script_path, trusted_dir)` (module-level); `ProcessorHook(script_path=None, trusted_dir=None)`; config key `trusted_processors_dir`.

- [ ] **Step 1: Write the failing validator test**

Create `tests/unit/test_hook_path_validation.py`:

```python
import os
import pytest

from extensibility_hooks import resolve_trusted_script


@pytest.mark.unit
def test_accepts_file_inside_trusted_dir(tmp_path):
    trusted = tmp_path / "processors"
    trusted.mkdir()
    script = trusted / "validate.py"
    script.write_text("result = {'continue': True}\n")
    resolved = resolve_trusted_script(str(script), str(trusted))
    assert resolved == os.path.realpath(str(script))


@pytest.mark.unit
def test_rejects_none_trusted_dir_fail_closed(tmp_path):
    script = tmp_path / "x.py"
    script.write_text("result = {}\n")
    assert resolve_trusted_script(str(script), None) is None


@pytest.mark.unit
def test_rejects_dotdot_escape(tmp_path):
    trusted = tmp_path / "processors"
    trusted.mkdir()
    outside = tmp_path / "evil.py"
    outside.write_text("result = {}\n")
    sneaky = os.path.join(str(trusted), "..", "evil.py")
    assert resolve_trusted_script(sneaky, str(trusted)) is None


@pytest.mark.unit
def test_rejects_absolute_path_outside(tmp_path):
    trusted = tmp_path / "processors"
    trusted.mkdir()
    outside = tmp_path / "evil.py"
    outside.write_text("result = {}\n")
    assert resolve_trusted_script(str(outside), str(trusted)) is None


@pytest.mark.unit
def test_rejects_nonexistent_file(tmp_path):
    trusted = tmp_path / "processors"
    trusted.mkdir()
    assert resolve_trusted_script(str(trusted / "missing.py"), str(trusted)) is None
```

- [ ] **Step 2: Run it — confirm ImportError/failure**

Run: `pytest tests/unit/test_hook_path_validation.py -v`
Expected: ERROR/FAIL — `resolve_trusted_script` does not exist yet.

- [ ] **Step 3: Implement the validator + wire the hooks**

In `src/extensibility_hooks.py`, after the imports (`import os`, add nothing new), insert the module-level function above the `ProcessorHook` class:

```python
def resolve_trusted_script(script_path, trusted_dir):
    """Resolve script_path and confirm it is a real file inside trusted_dir.

    Returns the resolved absolute path on success, else None (fail closed):
    None/empty trusted_dir or script_path, a path resolving outside the dir,
    or a non-file. Symlinks are resolved before the containment check.
    """
    if not trusted_dir or not script_path:
        return None
    base = os.path.realpath(trusted_dir)
    target = os.path.realpath(script_path)
    try:
        if os.path.commonpath([base, target]) != base:
            return None
    except ValueError:
        # Different drives on Windows -> not contained.
        return None
    if not os.path.isfile(target):
        return None
    return target
```

Change `ProcessorHook.__init__` to accept and store the trusted dir and use the validator:

```python
    def __init__(self, script_path=None, trusted_dir=None):
        self.script_path = script_path
        self.trusted_dir = trusted_dir
        self._resolved = resolve_trusted_script(script_path, trusted_dir)
        self.enabled = self._resolved is not None
```

In `ProcessorHook.execute`, replace the `# Create safe execution environment` block and the `open()` so it re-resolves right before running and refuses on failure:

```python
        # Re-resolve immediately before running (narrows TOCTOU).
        resolved = resolve_trusted_script(self.script_path, self.trusted_dir)
        if resolved is None:
            return {'continue': False,
                    'message': 'Processor script is not inside the trusted directory',
                    'error': True}

        # NOTE: this still runs the script with full builtins. It is NOT a
        # sandbox. The only protection is that the path is confined to an
        # admin-owned trusted-processors directory (SP4 / issue C2). Anyone
        # who can write that directory can run code in this process.
        hook_globals = {
            '__builtins__': __builtins__,
            '__file__': resolved,
            '__name__': '__processor_hook__',
            'context': context,
        }

        with open(resolved, 'r') as f:
            script_code = f.read()
```

Update `ProcessorManager.__init__` and `reload_hooks` to pass the trusted dir into every hook:

```python
    def __init__(self, config):
        self.config = config
        trusted = config.get('trusted_processors_dir')
        self.pre_ingest = PreIngestHook(config.get('pre_ingest_processor'), trusted)
        self.post_ingest = PostIngestHook(config.get('post_ingest_processor'), trusted)
        self.post_import = PostImportHook(config.get('post_import_processor'), trusted)
```

(apply the identical three-line change inside `reload_hooks`, reading `self.config`).

- [ ] **Step 4: Add the config key**

In `src/config.py`, inside `DEFAULT_CONFIG`, in the `# Processor hooks` block, add:

```python
        'trusted_processors_dir': None,  # admin-owned dir; None => hooks disabled (SP4/C2)
```

- [ ] **Step 5: Run the test — confirm green**

Run: `pytest tests/unit/test_hook_path_validation.py -v`
Expected: PASS (5 passed).

- [ ] **Step 6: Commit**

```bash
git add src/extensibility_hooks.py src/config.py tests/unit/test_hook_path_validation.py
git commit -m "fix(C2): confine processor exec() to trusted-processors dir; drop 'safe' claim"
```

---

## Task 2: C3 — Pin + checksum ffmpeg, sanitize extraction

**Files:**
- Modify: `tools/ffmpeg_downloader.py`
- Create: `tests/unit/test_ffmpeg_downloader_security.py`

**Interfaces:**
- Produces: `verify_checksum(path, expected_sha256)`, `_is_within_directory(directory, target)`, `safe_extract(archive, dest)`; `DOWNLOAD_SOURCES` records carrying `{"url", "sha256"}`; fail-closed `main`.

- [ ] **Step 1: Write the failing security tests**

Create `tests/unit/test_ffmpeg_downloader_security.py`:

```python
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
```

- [ ] **Step 2: Run it — confirm failure**

Run: `pytest tests/unit/test_ffmpeg_downloader_security.py -v`
Expected: FAIL — `verify_checksum`, `_is_within_directory`, `safe_extract` do not exist.

- [ ] **Step 3: Implement the helpers**

In `tools/ffmpeg_downloader.py`, add `import hashlib` and `import hmac` to the imports, then add:

```python
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
```

- [ ] **Step 4: Run the helper tests — confirm green**

Run: `pytest tests/unit/test_ffmpeg_downloader_security.py -v`
Expected: PASS (6 passed).

- [ ] **Step 5: Pin URLs + record checksums, wire `main` fail-closed**

Replace `DOWNLOAD_SOURCES` (macOS entries removed) with pinned versioned artifacts carrying a checksum slot:

```python
DOWNLOAD_SOURCES = {
    ("Windows", "AMD64"): {
        "url": "https://www.gyan.dev/ffmpeg/builds/packages/ffmpeg-7.0.2-essentials_build.zip",
        "sha256": "",   # filled in Step 6 from the pinned artifact
    },
    ("Linux", "x86_64"): {
        "url": "https://johnvansickle.com/ffmpeg/old-releases/ffmpeg-7.0.2-amd64-static.tar.xz",
        "sha256": "",   # filled in Step 6 from the pinned artifact
    },
}
```

Replace the old `extract()` call and the checksum-less flow inside `main()`. After `download(url, archive)`:

```python
        record = DOWNLOAD_SOURCES.get((sysname, arch))
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
```

Update the `urls = DOWNLOAD_SOURCES.get(...)` lookup earlier in `main` to read the record dict (`record = DOWNLOAD_SOURCES.get((sysname, arch))`; `if not record: ... sys.exit(1)`), and delete the old `extract()` function and its bare `except`.

- [ ] **Step 6: Record the real checksums (one-time data acquisition)**

For each pinned URL, download once and record the digest, then paste it into the `sha256` fields:

```bash
python - <<'PY'
import hashlib, urllib.request
for url in [
    "https://www.gyan.dev/ffmpeg/builds/packages/ffmpeg-7.0.2-essentials_build.zip",
    "https://johnvansickle.com/ffmpeg/old-releases/ffmpeg-7.0.2-amd64-static.tar.xz",
]:
    h = hashlib.sha256()
    with urllib.request.urlopen(url) as r:
        for chunk in iter(lambda: r.read(1024 * 1024), b""):
            h.update(chunk)
    print(url, h.hexdigest())
PY
```

Expected: two `url  <64-hex>` lines. Paste each digest into the matching `sha256` field. If a pinned version 404s, bump to the nearest existing version tag on the same host and re-run. (This is the only step that touches the network; it is a manual, one-time record — never run in CI.)

- [ ] **Step 7: Add a mocked-network fail-closed test**

Append to `tests/unit/test_ffmpeg_downloader_security.py`:

```python
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
```

Run: `pytest tests/unit/test_ffmpeg_downloader_security.py -v`
Expected: PASS (7 passed). The mismatch aborts with exit code 1 and never extracts.

- [ ] **Step 8: Commit**

```bash
git add tools/ffmpeg_downloader.py tests/unit/test_ffmpeg_downloader_security.py
git commit -m "fix(C3): pin+checksum ffmpeg download, sanitize extraction, remove bare except"
```

---

## Task 3: H2 — Salted PBKDF2 passwords + no default admin

**Files:**
- Modify: `src/db_manager.py`
- Create: `tests/unit/test_password_hashing.py`

**Interfaces:**
- Produces: `hash_password(password, iterations=..., salt=None)`, `verify_password(stored, password)`, `is_legacy_hash(stored)` (module-level); rewired `create_user`/`authenticate_user`/`change_user_password`; random admin seed; `must_change_password` column (Migration 7).

- [ ] **Step 1: Write the failing hashing tests**

Create `tests/unit/test_password_hashing.py`:

```python
import pytest

from db_manager import hash_password, verify_password, is_legacy_hash


@pytest.mark.unit
def test_pbkdf2_round_trip():
    stored = hash_password("s3cret")
    assert stored.startswith("pbkdf2_sha256$")
    assert verify_password(stored, "s3cret") is True


@pytest.mark.unit
def test_wrong_password_rejected():
    stored = hash_password("s3cret")
    assert verify_password(stored, "nope") is False


@pytest.mark.unit
def test_salt_is_random_per_hash():
    assert hash_password("same") != hash_password("same")


@pytest.mark.unit
def test_is_legacy_hash_detects_bare_sha256():
    import hashlib
    legacy = hashlib.sha256(b"admin").hexdigest()
    assert is_legacy_hash(legacy) is True
    assert is_legacy_hash(hash_password("admin")) is False


@pytest.mark.unit
def test_verify_password_accepts_legacy_hash():
    import hashlib
    legacy = hashlib.sha256("admin".encode("utf-8")).hexdigest()
    assert verify_password(legacy, "admin") is True
    assert verify_password(legacy, "wrong") is False
```

- [ ] **Step 2: Run it — confirm failure**

Run: `pytest tests/unit/test_password_hashing.py -v`
Expected: FAIL — the three functions don't exist.

- [ ] **Step 3: Implement the module-level password functions**

At the top of `src/db_manager.py`, below the existing imports, add:

```python
import hashlib
import hmac
import secrets

_PBKDF2_ITERATIONS = 260000


def hash_password(password, iterations=_PBKDF2_ITERATIONS, salt=None):
    """Return a self-describing salted PBKDF2 hash: pbkdf2_sha256$iters$salt$hash."""
    if salt is None:
        salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, iterations)
    return 'pbkdf2_sha256${0}${1}${2}'.format(iterations, salt.hex(), dk.hex())


def is_legacy_hash(stored):
    """True for the old unsalted format: a bare 64-char hex sha256 digest."""
    return bool(stored) and '$' not in stored and len(stored) == 64


def verify_password(stored, password):
    """Constant-time verify against a PBKDF2 or a legacy unsalted-sha256 hash."""
    if not stored:
        return False
    if is_legacy_hash(stored):
        legacy = hashlib.sha256(password.encode('utf-8')).hexdigest()
        return hmac.compare_digest(legacy, stored)
    try:
        scheme, iters, salt_hex, hash_hex = stored.split('$')
    except ValueError:
        return False
    if scheme != 'pbkdf2_sha256':
        return False
    dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'),
                             bytes.fromhex(salt_hex), int(iters))
    return hmac.compare_digest(dk.hex(), hash_hex)
```

- [ ] **Step 4: Run the hashing tests — confirm green**

Run: `pytest tests/unit/test_password_hashing.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Rewire create/change/authenticate**

In `create_user` (`~:1503`), remove the local `import hashlib` and replace the hash line:

```python
        password_hash = hash_password(password)
```

In `change_user_password` (`~:1638`), same replacement:

```python
        password_hash = hash_password(new_password)
```

Replace the body of `authenticate_user` (`~:1520`) with a fetch-then-verify (constant-time) + legacy upgrade:

```python
    def authenticate_user(self, username, password):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM users WHERE username = ? AND is_active = 1",
                (username,)
            )
            row = cursor.fetchone()
            if row is None:
                return None

            stored = row['password_hash']
            if not verify_password(stored, password):
                return None

            # Transparent upgrade of a legacy unsalted hash on successful login.
            if is_legacy_hash(stored):
                try:
                    cursor.execute(
                        "UPDATE users SET password_hash = ? WHERE user_id = ?",
                        (hash_password(password), row['user_id'])
                    )
                except sqlite3.Error:
                    self._log("Password upgrade failed (read-only?); login allowed")

            cursor.execute(
                "UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE user_id = ?",
                (row['user_id'],)
            )
            conn.commit()
            return dict(row)
```

- [ ] **Step 6: Write the legacy-upgrade DB test**

Create `tests/unit/test_auth_legacy_upgrade.py`:

```python
import hashlib
import pytest


@pytest.mark.unit
def test_legacy_hash_upgrades_on_login(stax_db):
    # Insert a user with an OLD unsalted sha256 hash directly.
    legacy = hashlib.sha256("hunter2".encode("utf-8")).hexdigest()
    with stax_db.get_connection() as conn:
        conn.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            ("legacy_user", legacy, "user"),
        )
        conn.commit()

    user = stax_db.authenticate_user("legacy_user", "hunter2")
    assert user is not None

    with stax_db.get_connection() as conn:
        row = conn.execute(
            "SELECT password_hash FROM users WHERE username = ?",
            ("legacy_user",),
        ).fetchone()
    assert row["password_hash"].startswith("pbkdf2_sha256$")


@pytest.mark.unit
def test_wrong_password_still_rejected(stax_db):
    stax_db.create_user("bob", "correct-horse", role="user")
    assert stax_db.authenticate_user("bob", "correct-horse") is not None
    assert stax_db.authenticate_user("bob", "wrong") is None
```

Run: `pytest tests/unit/test_auth_legacy_upgrade.py -v`
Expected: PASS (2 passed).

- [ ] **Step 7: Eliminate default admin/admin + add `must_change_password`**

Add a helper method to `DatabaseManager` (near the user methods):

```python
    def _seed_initial_admin(self, cursor):
        """Create the initial admin with a RANDOM password (never admin/admin).

        The password is logged once so a deployer can capture it; the account
        is flagged must_change_password so the login UI forces a reset (SP4/H2).
        """
        initial = secrets.token_urlsafe(12)
        cursor.execute(
            "INSERT INTO users (username, password_hash, role, must_change_password) "
            "VALUES (?, ?, ?, 1)",
            ("admin", hash_password(initial), "admin"),
        )
        self._log("Initial admin created. One-time password: {0} "
                  "(change on first login)".format(initial))
```

Replace the schema-create default-admin block (`~:347-355`) with:

```python
            cursor.execute("SELECT COUNT(*) as count FROM users")
            if cursor.fetchone()['count'] == 0:
                self._seed_initial_admin(cursor)
```

Replace the Migration 3 default-admin insert (`~:424-431`) with a call to `self._seed_initial_admin(cursor)` after the `CREATE TABLE users` (add the `must_change_password INTEGER DEFAULT 0` column to that inline `CREATE TABLE` and to the Table-8 `CREATE TABLE` at `~:296`). Then add **Migration 7** at the end of `_apply_migrations`:

```python
            # Migration 7: add must_change_password to users (SP4/H2)
            try:
                cursor.execute("SELECT must_change_password FROM users LIMIT 1")
                self._log("Migration 7: must_change_password already exists")
            except sqlite3.OperationalError:
                self._log("Migration 7: Adding must_change_password to users")
                cursor.execute(
                    "ALTER TABLE users ADD COLUMN must_change_password INTEGER DEFAULT 0"
                )
                self._log("Migration 7: Complete")
```

- [ ] **Step 8: Write the no-default-creds test**

Create `tests/unit/test_no_default_admin.py`:

```python
import pytest


@pytest.mark.unit
def test_admin_admin_credentials_do_not_work(stax_db):
    # An 'admin' user exists, but NOT with the password 'admin'.
    assert stax_db.get_user_by_username("admin") is not None
    assert stax_db.authenticate_user("admin", "admin") is None


@pytest.mark.unit
def test_admin_flagged_must_change_password(stax_db):
    admin = stax_db.get_user_by_username("admin")
    assert admin["must_change_password"] == 1
```

Run: `pytest tests/unit/test_no_default_admin.py -v`
Expected: PASS (2 passed). `admin`/`admin` is rejected; the seeded admin carries the reset flag.

- [ ] **Step 9: Run the whole auth surface + commit**

Run: `pytest tests/unit/test_password_hashing.py tests/unit/test_auth_legacy_upgrade.py tests/unit/test_no_default_admin.py -v`
Expected: all PASS.

```bash
git add src/db_manager.py tests/unit/test_password_hashing.py tests/unit/test_auth_legacy_upgrade.py tests/unit/test_no_default_admin.py
git commit -m "fix(H2): salted PBKDF2 passwords, legacy upgrade-on-login, remove default admin/admin"
```

---

## Task 4: H6 — Geometry viewer allow-list + shutdown

**Files:**
- Modify: `src/geometry_viewer.py`
- Create: `tests/unit/test_geometry_viewer_security.py`

**Interfaces:**
- Produces: `_is_within(base, target)` (module-level), `GeometryViewerServer.register_model(model_path)`, `/model/` 403 for unregistered paths, `GeometryViewerServer.shutdown()` + `shutdown_instance()`.

- [ ] **Step 1: Write the failing allow-list tests**

Create `tests/unit/test_geometry_viewer_security.py`:

```python
import os
import pytest

from geometry_viewer import _is_within, GeometryViewerServer


@pytest.mark.unit
def test_is_within_accepts_and_rejects(tmp_path):
    base = tmp_path / "previews"
    base.mkdir()
    assert _is_within(str(base), str(base / "a" / "m.glb")) is True
    assert _is_within(str(base), str(tmp_path / "outside.glb")) is False
    assert _is_within(str(base), os.path.join(str(base), "..", "x.glb")) is False


@pytest.mark.unit
def test_register_model_accepts_inside_previews(tmp_path):
    previews = tmp_path / "previews"
    previews.mkdir()
    glb = previews / "asset.glb"
    glb.write_bytes(b"glTF")
    srv = GeometryViewerServer.__new__(GeometryViewerServer)
    srv._init_registry(str(tmp_path), str(previews))
    assert srv.register_model(str(glb)) == os.path.realpath(str(glb))
    assert os.path.realpath(str(glb)) in srv._allowed


@pytest.mark.unit
def test_register_model_rejects_outside_previews(tmp_path):
    previews = tmp_path / "previews"
    previews.mkdir()
    outside = tmp_path / "secret.glb"
    outside.write_bytes(b"glTF")
    srv = GeometryViewerServer.__new__(GeometryViewerServer)
    srv._init_registry(str(tmp_path), str(previews))
    assert srv.register_model(str(outside)) is None


@pytest.mark.unit
def test_register_model_rejects_nonexistent(tmp_path):
    previews = tmp_path / "previews"
    previews.mkdir()
    srv = GeometryViewerServer.__new__(GeometryViewerServer)
    srv._init_registry(str(tmp_path), str(previews))
    assert srv.register_model(str(previews / "missing.glb")) is None
```

Note: the tests construct the server via `__new__` + `_init_registry` to exercise the pure allow-list logic **without** binding a socket or starting a thread.

- [ ] **Step 2: Run it — confirm failure**

Run: `pytest tests/unit/test_geometry_viewer_security.py -v`
Expected: FAIL — `_is_within`, `_init_registry`, `register_model` don't exist.

- [ ] **Step 3: Implement the containment helper + registry**

In `src/geometry_viewer.py`, after `_norm` (`~:48`), add:

```python
import threading  # (already imported at top; keep single import)


def _is_within(base, target):
    base_r = os.path.realpath(base)
    target_r = os.path.realpath(target)
    try:
        return os.path.commonpath([base_r, target_r]) == base_r
    except ValueError:
        return False
```

Give `GeometryViewerServer` a registry initializer and `register_model`. Add a `previews_root` parameter to `__init__` and call `_init_registry`:

```python
    def __init__(self, project_root, previews_root=None):
        self._init_registry(project_root, previews_root)
        handler_cls = _make_handler(
            self._viewer_dir, self._dependencies_root, self._project_root,
            self._previews_root, self._allowed,
        )
        self._port = _find_free_port()
        self._httpd = _ThreadingHTTPServer(('127.0.0.1', self._port), handler_cls)
        self._thread = threading.Thread(target=self._httpd.serve_forever)
        self._thread.daemon = True
        self._thread.start()

    def _init_registry(self, project_root, previews_root):
        self._project_root = _norm(project_root)
        self._viewer_dir = os.path.join(self._project_root, 'resources', 'geometry_viewer')
        self._dependencies_root = os.path.join(self._project_root, 'dependencies')
        if previews_root:
            self._previews_root = _norm(previews_root)
        else:
            self._previews_root = os.path.join(self._project_root, 'previews')
        self._allowed = set()
        self._reg_lock = threading.Lock()

    def register_model(self, model_path):
        if not model_path:
            return None
        resolved = _norm(model_path)
        if not (os.path.isfile(resolved) and _is_within(self._previews_root, resolved)):
            return None
        with self._reg_lock:
            self._allowed.add(resolved)
        return resolved
```

Update `.instance()` to accept and forward `previews_root`:

```python
    @classmethod
    def instance(cls, project_root, previews_root=None):
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls(project_root, previews_root)
            return cls._instance
```

- [ ] **Step 4: Enforce the allow-list in the handler + endpoints**

Change `_make_handler` signature to `_make_handler(viewer_dir, dependencies_root, project_root, previews_root, allowed)`, `_norm` the previews root, and in the `/model/` branch of `do_GET`, after `model_path = _norm(model_path)` and the existence check, add:

```python
                if model_path not in allowed or not _is_within(previews_root, model_path):
                    self.send_error(403, "Model not permitted")
                    return
```

Make `model_endpoint` register before minting a token:

```python
    def model_endpoint(self, model_path):
        if not model_path:
            return None
        resolved = self.register_model(model_path)
        if not resolved:
            return None
        try:
            token = base64.urlsafe_b64encode(resolved.encode('utf-8')).rstrip(b'=')
            quoted = quote(token.decode('ascii'))
            return 'http://127.0.0.1:{0}/model/{1}'.format(self._port, quoted)
        except Exception:
            return None
```

Also tighten `translate_path`'s final fallthrough (the `project_root` branch) to reject escapes:

```python
            rel = unquote(resource.lstrip('/'))
            target = _norm(os.path.join(project_root, rel))
            if not _is_within(project_root, target):
                return _norm(os.path.join(project_root, 'viewer', 'index.html'))
            return target
```

- [ ] **Step 5: Add the shutdown hook**

Add to `GeometryViewerServer`:

```python
    def shutdown(self):
        try:
            self._httpd.shutdown()
            self._httpd.server_close()
        except Exception:
            pass
        if self._thread is not None:
            self._thread.join(timeout=3)

    @classmethod
    def shutdown_instance(cls):
        with cls._lock:
            if cls._instance is not None:
                cls._instance.shutdown()
                cls._instance = None
```

Wire `GeometryViewerWidget` to expose and use it: pass the previews root into `_ensure_server` (`GeometryViewerServer.instance(self._project_root, self._previews_root)` — store `self._previews_root` from a new `previews_root=None` `__init__` kwarg, defaulting under `project_root`), and add:

```python
    def shutdown(self):
        GeometryViewerServer.shutdown_instance()

    def closeEvent(self, event):
        self.shutdown()
        super(GeometryViewerWidget, self).closeEvent(event)
```

- [ ] **Step 6: Run the security tests — confirm green**

Run: `pytest tests/unit/test_geometry_viewer_security.py -v`
Expected: PASS (5 passed).

- [ ] **Step 7: Commit**

```bash
git add src/geometry_viewer.py tests/unit/test_geometry_viewer_security.py
git commit -m "fix(H6): allow-list geometry /model/ to previews root, add server shutdown hook"
```

---

## Task 5: M2 — Constant-time API token + ingest allow-list

**Files:**
- Modify: `src/api_server.py`, `src/config.py`
- Create: `tests/unit/test_api_security.py`

**Interfaces:**
- Produces: `hmac.compare_digest` token checks in both backends; `path_within_roots(filepath, roots)` (module-level); config key `api_ingest_roots`.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_api_security.py`:

```python
import pytest

from api_server import _build_flask_app, path_within_roots


@pytest.mark.unit
def test_path_within_roots_accepts_and_rejects(tmp_path):
    root = tmp_path / "ingest"
    root.mkdir()
    ok = root / "plate.exr"
    ok.write_bytes(b"x")
    outside = tmp_path / "secret.exr"
    outside.write_bytes(b"x")
    assert path_within_roots(str(ok), [str(root)]) is True
    assert path_within_roots(str(outside), [str(root)]) is False
    assert path_within_roots(str(ok), []) is False  # empty roots => deny


def _client(stax_db, stax_config):
    stax_config.set("api_token", "right-token")
    app = _build_flask_app(stax_db, stax_config)
    app.testing = True
    return app.test_client()


@pytest.mark.gui
def test_wrong_token_rejected(stax_db, stax_config):
    client = _client(stax_db, stax_config)
    resp = client.get("/api/v1/stacks", headers={"X-StaX-Token": "wrong"})
    assert resp.status_code == 401


@pytest.mark.gui
def test_empty_token_rejected(stax_db, stax_config):
    client = _client(stax_db, stax_config)
    resp = client.get("/api/v1/stacks", headers={"X-StaX-Token": ""})
    assert resp.status_code == 401


@pytest.mark.gui
def test_right_token_accepted(stax_db, stax_config):
    client = _client(stax_db, stax_config)
    resp = client.get("/api/v1/stacks", headers={"X-StaX-Token": "right-token"})
    assert resp.status_code == 200


@pytest.mark.gui
def test_ingest_rejects_path_outside_roots(stax_db, stax_config, tmp_path):
    outside = tmp_path / "evil.exr"
    outside.write_bytes(b"x")
    stax_config.set("api_ingest_roots", [str(tmp_path / "allowed")])
    client = _client(stax_db, stax_config)
    resp = client.post(
        "/api/v1/elements/ingest",
        headers={"X-StaX-Token": "right-token"},
        json={"filepath": str(outside), "list_id": 1},
    )
    assert resp.status_code == 403
```

- [ ] **Step 2: Run it — confirm failure**

Run: `pytest tests/unit/test_api_security.py -v`
Expected: FAIL — `path_within_roots` missing; the ingest route does not 403 yet.

- [ ] **Step 3: Implement constant-time auth + the allow-list**

In `src/api_server.py`, add `import hmac` near the top imports, then add a module-level helper below `_GLOBAL_SERVER`:

```python
def path_within_roots(filepath, roots):
    """True iff filepath resolves inside at least one of roots (realpath check)."""
    if not filepath or not roots:
        return False
    target = os.path.realpath(filepath)
    for root in roots:
        base = os.path.realpath(root)
        try:
            if os.path.commonpath([base, target]) == base:
                return True
        except ValueError:
            continue
    return False
```

In `_build_flask_app`, replace the `require_auth` comparison (`~:91`):

```python
            provided = request.headers.get("X-StaX-Token", "")
            if not token or not provided or not hmac.compare_digest(provided, token):
                abort(401)
```

In the `ingest` route, after the `isfile` check (`~:161`), add the allow-list guard before building `IngestionCore`:

```python
        roots = config.get("api_ingest_roots", []) or []
        if not path_within_roots(filepath, roots):
            return jsonify({"error": "filepath outside permitted ingest roots"}), 403
```

In `_SimpleHandler.__call__` (`~:229`), replace the fallback token check:

```python
        configured = self.config.get("api_token", "")
        if not configured or not hmac.compare_digest(token, configured):
            return respond("401 Unauthorized", {"error": "invalid token"})
```

- [ ] **Step 4: Add the config key**

In `src/config.py` `DEFAULT_CONFIG`, add under the search/identity area:

```python
        'api_ingest_roots': [],  # allow-list of dirs the REST API may ingest from (SP4/M2)
```

- [ ] **Step 5: Run the tests — confirm green**

Run: `pytest tests/unit/test_api_security.py -v`
Expected: PASS (6 passed). Wrong/empty tokens 401; right token 200; out-of-root ingest 403.

- [ ] **Step 6: Commit**

```bash
git add src/api_server.py src/config.py tests/unit/test_api_security.py
git commit -m "fix(M2): constant-time API token compare (both backends), ingest-path allow-list"
```

---

## Task 6: L9 — CLI HTTPS + env-var token precedence

**Files:**
- Modify: `tools/stax_cli.py`
- Create: `tests/unit/test_stax_cli_security.py`

**Interfaces:**
- Produces: `_base(host, port, scheme='http')`, `resolve_token(cli_token)` (env over argv), `--https`/`STAX_API_SCHEME`.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_stax_cli_security.py`:

```python
import os
import sys

import pytest

_TOOLS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "tools",
)
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

import stax_cli


@pytest.mark.unit
def test_base_builds_https_url():
    assert stax_cli._base("host", 443, "https") == "https://host:443/api/v1"


@pytest.mark.unit
def test_base_defaults_to_http():
    assert stax_cli._base("127.0.0.1", 17171) == "http://127.0.0.1:17171/api/v1"


@pytest.mark.unit
def test_env_token_wins_over_argv(monkeypatch):
    monkeypatch.setenv("STAX_API_TOKEN", "from-env")
    assert stax_cli.resolve_token("from-argv") == "from-env"


@pytest.mark.unit
def test_argv_token_used_when_env_absent(monkeypatch):
    monkeypatch.delenv("STAX_API_TOKEN", raising=False)
    assert stax_cli.resolve_token("from-argv") == "from-argv"
```

- [ ] **Step 2: Run it — confirm failure**

Run: `pytest tests/unit/test_stax_cli_security.py -v`
Expected: FAIL — `_base` takes 2 args; `resolve_token` missing.

- [ ] **Step 3: Implement scheme + token precedence**

In `tools/stax_cli.py`, replace `_base` (`~:124`):

```python
def _base(host, port, scheme="http"):
    return "{}://{}:{}/api/v1".format(scheme, host, port)


def resolve_token(cli_token):
    """Prefer the STAX_API_TOKEN env var over a token passed in argv."""
    return os.environ.get("STAX_API_TOKEN") or cli_token or ""
```

In `_build_parser` (`~:311`), add a scheme option and note the env override:

```python
    p.add_argument(
        "--scheme",
        default=os.environ.get("STAX_API_SCHEME", "http"),
        choices=["http", "https"],
        help="URL scheme (default: http; env STAX_API_SCHEME)",
    )
    p.add_argument(
        "--https",
        action="store_const", const="https", dest="scheme",
        help="Shortcut for --scheme https",
    )
```

Update every `_base(args.host, args.port)` call in the `cmd_*` functions to `_base(args.host, args.port, args.scheme)`. In `main()` (`~:398`), resolve the token from the environment first and warn only when neither source has one:

```python
    args.token = resolve_token(args.token)
    if not args.token and args.command != "health":
        print("WARNING: No auth token set.  "
              "Prefer the STAX_API_TOKEN env var over --token.")
```

- [ ] **Step 4: Run the tests — confirm green**

Run: `pytest tests/unit/test_stax_cli_security.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add tools/stax_cli.py tests/unit/test_stax_cli_security.py
git commit -m "fix(L9): CLI HTTPS support and STAX_API_TOKEN precedence over argv"
```

---

## Task 7: Full-suite verification

**Files:** none (verification only).

- [ ] **Step 1: Run the entire collected suite**

Run: `pytest -m "not manual"`
Expected: all SP4 unit/gui tests PASS; **0 failed, 0 errored**. Pre-existing SP0 `xfail`s remain `xfail` (SP4 does not touch C1). If any SP4 test errors on a missing fixture, confirm Task ordering and that `tests/conftest.py` is the SP0 version.

- [ ] **Step 2: Confirm no bare `except` or "safe execution" claim remains**

Run:
```bash
grep -rn "safe execution environment" src/ ; grep -n "except:" tools/ffmpeg_downloader.py
```
Expected: no matches (the misleading comment and the bare `except:` are gone).

- [ ] **Step 3: Push and confirm CI is green**

```bash
git push
gh run watch
```
Expected: both matrix jobs (`ubuntu-latest`, `windows-latest`) conclude `success`. If a job fails, read `gh run view --log-failed` and fix the root cause — never weaken a security test to pass.

---

## Self-Review

**1. Spec coverage:**
- C2 restrict+validate, honest comment, fail-closed → Task 1 ✓
- C3 pin+checksum, `safe_extract`, no bare except, fail-closed main → Task 2 ✓
- H2 PBKDF2+salt, legacy upgrade-on-login, no default admin, `must_change_password` → Task 3 ✓
- H6 previews-root allow-list, `register_model`, `/model/` 403, shutdown hook → Task 4 ✓
- M2 `hmac.compare_digest` (Flask + wsgiref), ingest-path allow-list → Task 5 ✓
- L9 HTTPS scheme + env-token precedence → Task 6 ✓
- New config keys `trusted_processors_dir`, `api_ingest_roots` → Tasks 1, 5 ✓
- Pure-logic tests (accept/reject tables, round-trips, mocked `urlopen`, `tmp_path`/`monkeypatch`) → every task ✓

**2. Placeholder scan:** No "TBD/TODO/handle appropriately". Every code step is complete. The only externally-sourced data (C3 SHA-256 digests) is acquired by an explicit one-time command in Task 2 Step 6 with a documented fallback; the verification logic itself is complete and tested against locally-built archives.

**3. Type/signature consistency:** `resolve_trusted_script(script_path, trusted_dir)`, `verify_checksum(path, expected_sha256)`, `safe_extract(archive, dest)`, `hash_password(password,...)`/`verify_password(stored, password)`/`is_legacy_hash(stored)`, `GeometryViewerServer.register_model(model_path)` + `_is_within(base, target)`, `path_within_roots(filepath, roots)`, `_base(host, port, scheme)`/`resolve_token(cli_token)` — all match the "Key signatures" section and the real call sites (`ProcessorManager(config_dict)`, `_build_flask_app(db, config)`, `authenticate_user(username, password)`, `DatabaseManager` `users` columns). Config access uses `.get`, honored by both `Config` and dict. Fixtures (`stax_db`, `stax_config`, `tmp_path`, `monkeypatch`) are the SP0 ones.

**4. Fail-closed audit:** every new default denies — `trusted_processors_dir=None` ⇒ hooks off; `api_ingest_roots=[]` ⇒ ingest 403; empty/absent token ⇒ 401; unregistered/out-of-root model ⇒ 403; checksum mismatch/traversing member ⇒ abort.

---

## Notes for the executor
- **Do not** add subprocess/Pyblish sandboxing (C2) or hash the stored API token (M2) — out of scope; SP4 restricts inputs only.
- **Do not** fix H1/M1/M9 or any non-SP4 defect surfaced by a test; note it and move on.
- Run `pytest -m "not manual"` before each commit. Never weaken a security assertion to make CI pass — fix the root cause.
- C3 Step 6 is the only network touch and is manual/one-time; CI and unit tests always mock `urlopen`.
