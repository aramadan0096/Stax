# SP4 — Security Hardening — Design

**Date:** 2026-07-22
**Status:** Approved (design)
**Part of:** the StaX audit-remediation program (9 sub-projects, SP0–SP8). SP4 closes the security holes surfaced by the audit. It builds on the SP0 test harness (real-schema `stax_db`, headless Qt, `tmp_path`/`monkeypatch`, mocked network) and depends on SP1 (DB consolidation) only where noted.

---

## 1. Background & Motivation

The StaX audit (`STAX_AUDIT_REPORT.md`) found six exploitable or unsafe code paths that share one theme: **untrusted input reaches a dangerous sink with no validation**. Each is independently shippable:

| ID | File | Danger | Sink |
|---|---|---|---|
| **C2** | `src/extensibility_hooks.py:42-55` | Arbitrary code execution | `exec(script_code, {'__builtins__': __builtins__})` on a config-supplied path |
| **C3** | `tools/ffmpeg_downloader.py:43-62` | Zip-Slip + unverified binary | `extractall()` with no filter; no checksum; bare `except:` |
| **H2** | `src/db_manager.py:346-355,425-431,1503,1533,1640` | Offline password cracking + default creds | unsalted `sha256(password)`; auto-created `admin`/`admin` |
| **H6** | `src/geometry_viewer.py:75-90,96-143` | Arbitrary local-file read + thread leak | `/model/<b64>` streams any absolute path; `serve_forever` never stopped |
| **M2** | `src/api_server.py:91,229,152-175` | Timing side-channel + arbitrary-file ingest | `provided != token`; `filepath` from body ingested after only `isfile` |
| **L9** | `tools/stax_cli.py:87,124-125` | Token in argv + plaintext HTTP | `--token` on the command line; `http://` only |

**Locked decisions for SP4 (do not relitigate):**
- **C2:** *restrict + validate, keep `exec`.* Load processor scripts **only** from a configurable admin-owned trusted-processors directory; validate the resolved real path is inside it; reject relative / network / `..` paths; remove the misleading "safe execution environment" comment. **No** Pyblish, **no** subprocess isolation in this SP.
- **C3:** pin exact versioned ffmpeg URLs; ship + verify a SHA-256 per platform (fail closed on mismatch); sanitize extraction — `filter="data"` on Py≥3.12, else per-member path validation; remove the bare `except`.
- **H2:** `hashlib.pbkdf2_hmac` (stdlib), per-user salt; store salt+hash+iterations; migrate legacy unsalted hashes on next successful login; eliminate the auto-created `admin`/`admin` (random initial password + forced reset). **No new dependency.**
- **H6:** restrict `/model/` to an allow-list of registered GLB paths inside a previews root; reject anything outside it; add a server shutdown hook.
- **M2:** `hmac.compare_digest` for the token check in **both** the Flask app and the `wsgiref` fallback; validate the ingest `filepath` against an allow-list of ingest roots.
- **L9:** support `https://` URLs; prefer the `STAX_API_TOKEN` env var over `--token` in argv.

---

## 2. Goals / Non-Goals

### Goals
- Every dangerous sink above is guarded by a **pure, unit-testable validation function** that a test can drive with `tmp_path`/`monkeypatch` and no network.
- Password storage migrates transparently: existing users keep logging in; their hashes upgrade to salted PBKDF2 on first success.
- No known default credentials ever ship; the initial admin password is random and one-time-logged, with a forced-reset flag.
- The ffmpeg installer fails **closed** on a checksum mismatch or a traversing archive member, with narrow (not bare) exception handling.
- The geometry HTTP server serves only explicitly-registered GLB files inside the previews root and can be shut down.
- The REST token comparison is constant-time in both server backends; API ingest is confined to configured roots.
- The CLI never requires a token in argv (env-var preferred) and speaks HTTPS.

### Non-Goals (explicitly deferred)
- **Real sandboxing** of processor hooks (subprocess/seccomp/Pyblish) — deferred; SP4 only restricts *where scripts load from*.
- Hashing/rotating the **stored** API token, or moving it out of `config.json` — M2 covers only the comparison and the ingest-path allow-list.
- Fixing the **file-lock race / WAL-on-share** (H1), SQL column-name injection (M1), or subprocess timeouts (M9) — those belong to SP1/SP3.
- TLS **server** support for the API (the API stays localhost HTTP); L9 only makes the *client* HTTPS-capable.
- bcrypt/argon2 (would add a dependency) — PBKDF2 is the locked choice.

---

## 3. Approach

**One issue, one commit, one pure validator.** Each fix extracts a small module-level function with no I/O side effects beyond the filesystem/DB it is handed, so the security property is asserted directly (accept/reject tables) rather than through a GUI or the network. Callers are then rewired to route through the validator. Tests live in `tests/unit/` (a couple touch `stax_db`, which is itself a `tmp_path` DB) and mock `urllib.request.urlopen` — never the real network.

Rejected alternatives:
- *Guard at the call sites inline* — scatters the security logic and makes it untestable without spinning up Qt/Flask.
- *Adopt Pyblish/bcrypt now* — out of scope per locked decisions; adds dependencies and risk.

---

## 4. Detailed Design

### 4.1 C2 — Restrict processor-script `exec()` to a trusted directory

**New config key** (add to `Config.DEFAULT_CONFIG`): `'trusted_processors_dir': None`. When `None`, hooks are **disabled** (fail closed): no trusted dir configured ⇒ no scripts execute.

**New module-level function in `src/extensibility_hooks.py`:**

```python
def resolve_trusted_script(script_path, trusted_dir):
    """Resolve script_path and confirm it is a real file inside trusted_dir.

    Returns the resolved absolute path on success, or None if:
      - trusted_dir is falsy (feature disabled / fail closed),
      - script_path is falsy,
      - the resolved path is not inside the resolved trusted_dir,
      - the resolved path is not an existing regular file.
    Symlinks are resolved (realpath) before the containment check so a
    symlink inside the dir cannot point outside it.
    """
    if not trusted_dir or not script_path:
        return None
    base = os.path.realpath(trusted_dir)
    target = os.path.realpath(script_path)
    try:
        common = os.path.commonpath([base, target])
    except ValueError:
        # Different drives on Windows -> not contained.
        return None
    if common != base:
        return None
    if not os.path.isfile(target):
        return None
    return target
```

`ProcessorHook.__init__` gains a `trusted_dir` parameter; `enabled` becomes `resolve_trusted_script(script_path, trusted_dir) is not None`. `execute()` re-resolves via the same function immediately before `open()`/`exec()` (TOCTOU-narrowing), refuses if it now returns `None`, and the misleading `# Create safe execution environment` comment is replaced with an honest one:

```python
# NOTE: this still runs the script with full builtins. It is NOT a sandbox.
# The only protection is that the path is confined to an admin-owned
# trusted-processors directory (SP4 / issue C2). Anyone who can write that
# directory can run code in this process.
```

`ProcessorManager.__init__` reads `config.get('trusted_processors_dir')` once and passes it into all three hooks; `reload_hooks` does the same. Relative, `..`, and UNC/`\\server\share` paths all fail the `commonpath` containment check because `os.path.realpath` anchors them and a network path shares no common prefix with a local trusted dir.

### 4.2 C3 — Pin + checksum ffmpeg, sanitize extraction

`tools/ffmpeg_downloader.py` changes:

- `DOWNLOAD_SOURCES` maps each **(system, arch)** to a `{"url": <pinned versioned url>, "sha256": <hex>}` record (macOS entries removed — Windows + Linux only). URLs are exact versioned artifacts, not `-release-` moving targets.
- New `verify_checksum(path, expected_sha256)` streams the file in 1 MB chunks through `hashlib.sha256` and returns `bool` via `hmac.compare_digest(actual, expected.lower())`.
- New `_is_within_directory(directory, target)` — the same realpath/`commonpath` containment check used in C2 (shared logic, duplicated locally to keep the downloader dependency-free).
- New `safe_extract(archive, dest)`:
  - zip/tar chosen by `zipfile.is_zipfile`.
  - On Python ≥ 3.12, call `extractall(dest, filter="data")` (rejects traversal, absolute paths, unsafe links).
  - On older Python, iterate members and raise `RuntimeError` if any member's join with `dest` escapes `dest` (`_is_within_directory` false), before extracting.
  - No bare `except:` — only `tarfile.TarError` / `zipfile.BadZipFile` are caught and re-raised as `RuntimeError` with context.
- `main()` verifies the checksum immediately after download and **aborts (`sys.exit(1)`) on mismatch before extraction**.

The pinned SHA-256 constants are obtained once from the pinned artifacts (implementation-plan Step records the exact command). Tests never touch the network: they build a local zip/tar in `tmp_path`, compute its checksum locally, and monkeypatch `urllib.request.urlopen` to serve those bytes — so both the checksum path and the traversal-rejection path are exercised deterministically.

### 4.3 H2 — Salted PBKDF2 + no default admin

**Stored-hash format** (single TEXT column, self-describing):

```
pbkdf2_sha256$<iterations>$<salt_hex>$<hash_hex>
```

**New module-level functions in `src/db_manager.py`** (importable flat as `from db_manager import hash_password, verify_password, is_legacy_hash`):

```python
import hashlib, hmac, os

_PBKDF2_ITERATIONS = 260000

def hash_password(password, iterations=_PBKDF2_ITERATIONS, salt=None):
    if salt is None:
        salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, iterations)
    return 'pbkdf2_sha256${0}${1}${2}'.format(iterations, salt.hex(), dk.hex())

def is_legacy_hash(stored):
    # Old format: a bare 64-char lowercase hex sha256 digest, no '$'.
    return bool(stored) and '$' not in stored and len(stored) == 64

def verify_password(stored, password):
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

**Rewired DB methods:**
- `create_user` / `change_user_password` call `hash_password(password)` instead of `sha256`.
- `authenticate_user` fetches the user by `username` + `is_active`, then verifies with `verify_password(row['password_hash'], password)` (constant-time). **On success with a legacy hash**, it re-hashes with PBKDF2 and `UPDATE`s `password_hash` in the same transaction (transparent upgrade), then updates `last_login`.
- **Default-admin elimination:** the two `admin`/`admin` inserts (schema-create ~L350 and Migration 3 ~L426) are replaced by a helper `_seed_initial_admin(cursor)` that generates `secrets.token_urlsafe(12)`, stores it via `hash_password`, sets a new `must_change_password` column to `1`, and logs the random password **once** through `stax_logger` (never persisted in plaintext). A new **Migration 7** adds `must_change_password INTEGER DEFAULT 0` to `users`. `authenticate_user`'s returned dict surfaces `must_change_password` so the login UI (SP6) can force a reset; SP4 only guarantees the flag and the random seed.

No schema-breaking change to the `password_hash` column (still TEXT); legacy rows remain readable and self-upgrade. This depends on nothing from SP1.

### 4.4 H6 — Geometry viewer allow-list + shutdown

`src/geometry_viewer.py` changes:

- `GeometryViewerServer.__init__` resolves a **previews root** (`_norm(previews_root)`, defaulting to `<project_root>/previews` when not supplied) and holds a thread-safe registry: `self._allowed = set()` guarded by `self._reg_lock = threading.Lock()`.
- New `register_model(model_path)`: `_norm`s the path, confirms it exists, is a file, and is **inside the previews root** (realpath/`commonpath` check via a shared `_is_within(base, target)` helper); on success adds it to `self._allowed` and returns the resolved path, else returns `None`.
- `model_endpoint` / `viewer_url_for_model` call `register_model` first and return `None` (→ placeholder) when registration fails, so only vetted paths ever get a token.
- The `/model/` handler, after decoding the token to `model_path` and `_norm`ing it, checks membership: `if model_path not in handler_allowed or not _is_within(previews_root, model_path): send_error(403)`. The registry and previews root are captured by `_make_handler`. `translate_path` for the non-`/viewer/`, non-`/dependencies/` fallthrough is tightened to also reject anything that escapes `project_root`.
- New `GeometryViewerServer.shutdown()` calls `self._httpd.shutdown()`, `self._httpd.server_close()`, and joins the thread with a timeout; a classmethod `shutdown_instance()` tears down the singleton and resets `_instance = None`. `GeometryViewerWidget` gains a `closeEvent`/`shutdown()` that calls it, wired from the owning widget's teardown (SP6 connects the parent; SP4 provides the hook).

`GeometryViewerWidget.load_geometry(glb_path)` passes the configured previews root down (via `GeometryViewerServer.instance(project_root, previews_root)`) and relies on `register_model` — a GLB outside the previews root now yields the "preview unavailable" placeholder instead of being served.

### 4.5 M2 — Constant-time token + ingest allow-list

`src/api_server.py` changes:

- **Flask app** `require_auth`: replace `provided != token` with
  `if not provided or not hmac.compare_digest(provided, token): abort(401)`.
- **wsgiref fallback** `_SimpleHandler.__call__`: replace `token != self.config.get(...)` with `hmac.compare_digest`. Both compare the UTF-8 bytes to avoid Unicode length leaks; empty configured token ⇒ always 401 (fail closed).
- New module-level `path_within_roots(filepath, roots)`: `_norm`s `filepath` and each root, returns `True` iff the file resolves inside at least one root (realpath/`commonpath`). Reads `roots` from `config.get('api_ingest_roots', [])` (new key; empty ⇒ no ingest allowed, fail closed).
- The `ingest` route, after the existing `isfile` check, calls `path_within_roots(filepath, config.get('api_ingest_roots', []))`; on failure returns `403 {"error": "filepath outside permitted ingest roots"}` **before** constructing `IngestionCore`.

`hmac` and the helper are pure; tests drive them directly and via Flask's `test_client` with right/wrong/empty tokens.

### 4.6 L9 — CLI HTTPS + env-var token

`tools/stax_cli.py` changes:
- `_base(host, port, scheme)` gains a `scheme` argument; a new `--https` flag (or `--scheme {http,https}`) and `STAX_API_SCHEME` env var select it (default `http` for localhost back-compat).
- **Token precedence:** `resolve_token(cli_token)` returns `os.environ.get('STAX_API_TOKEN')` when set, else the `--token` value — so a token in the environment always wins over argv, and the help text steers users to the env var. `main()` calls it and warns only when *neither* is present.

### 4.7 New config keys (summary)

| Key | Default | Used by |
|---|---|---|
| `trusted_processors_dir` | `None` | C2 — hook script confinement (None ⇒ hooks disabled) |
| `api_ingest_roots` | `[]` | M2 — API ingest allow-list (empty ⇒ ingest disabled) |

`previews_path` (already exists) supplies H6's previews root. No key that widens access defaults to "open".

---

## 5. Testing Strategy

Pure-logic security tests only — no network, no real Qt windows, no real ffmpeg. All use `tmp_path`/`monkeypatch`; `urllib.request.urlopen` is monkeypatched.

| Fix | Unit assertions |
|---|---|
| C2 | `resolve_trusted_script` accepts a file inside the trusted dir; rejects `..`, an absolute path outside, a relative path, a symlink escaping the dir, a nonexistent file, and `trusted_dir=None`. |
| C3 | `verify_checksum` true on match / false on one-bit change; `safe_extract` rejects a tar/zip member named `../evil` (raises) and extracts a clean archive; `main` aborts on checksum mismatch (mocked `urlopen`). |
| H2 | `verify_password(hash_password(pw), pw)` round-trips true; wrong password false; two hashes of the same password differ (random salt); `is_legacy_hash` true for a 64-hex digest; **legacy upgrade**: seed a user row with a bare `sha256` hash in `stax_db`, `authenticate_user` succeeds and the stored hash now starts `pbkdf2_sha256$`. |
| H6 | `register_model` accepts a GLB inside the previews root, rejects one outside, a `..` path, and a nonexistent file; `_is_within` accept/reject table. |
| M2 | `path_within_roots` accept/reject table; Flask `test_client` returns 401 for wrong/empty token and passes for the right token (constant-time path); ingest route 403s a filepath outside `api_ingest_roots`. |
| L9 | `resolve_token` prefers `STAX_API_TOKEN` over the argv value; `_base(..., scheme='https')` emits an `https://` URL. |

CI: these land in `tests/unit/` and run under the SP0 gate on Windows + Linux. Nothing here needs ffmpeg, Nuke, or a display.

---

## 6. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Windows `commonpath` raises `ValueError` across drives | Caught explicitly → treated as "not contained" (reject). |
| Legacy-hash upgrade write fails on a read-only share | Upgrade is best-effort inside the auth transaction; a failed `UPDATE` still returns the authenticated user (login not blocked), logged as a warning. |
| Pinned ffmpeg URL 404s later (upstream removes a version) | URLs point at versioned/`old-releases` artifacts; checksum failure is loud and the plan records the exact recompute command. |
| `filter="data"` unavailable < 3.12 | Explicit per-member containment fallback covers 3.9–3.11 (StaX's floor). |
| Existing callers pass a `Config` object where a dict is expected (H7-style) | SP4 reads keys through `.get`, which both `Config` and dict support; no behavioral coupling added. |
| Empty `api_ingest_roots` breaks existing API ingest users | Documented as intentional fail-closed; operators must configure roots — noted in the plan and release notes. |

---

## 7. Deliverables Checklist
- [ ] C2: `resolve_trusted_script` + `trusted_processors_dir` wiring; honest comment; hooks fail closed.
- [ ] C3: pinned+checksummed URLs, `verify_checksum`, `safe_extract`, bare `except` removed, fail-closed `main`.
- [ ] H2: `hash_password`/`verify_password`/`is_legacy_hash`; rewired create/auth/change; legacy upgrade-on-login; random admin seed + `must_change_password`.
- [ ] H6: previews-root allow-list, `register_model`, `/model/` 403, `shutdown()`/`shutdown_instance()`.
- [ ] M2: `hmac.compare_digest` in both backends; `path_within_roots` + `api_ingest_roots` on ingest.
- [ ] L9: `--https`/scheme + `STAX_API_SCHEME`; `resolve_token` env-over-argv precedence.
- [ ] New config keys `trusted_processors_dir`, `api_ingest_roots` added to `Config.DEFAULT_CONFIG`.
- [ ] Unit tests for every validator (accept/reject tables, round-trips, mocked `urlopen`), green under the SP0 CI gate.

---

## 8. Follow-on
SP5 (Nuke integration) consumes the C2 trusted-dir contract when it revisits the hook call sites; SP6 (UI correctness) wires H6's `shutdown()` into the geometry pane's `closeEvent` and adds the forced-password-reset dialog gated on `must_change_password`. Real hook sandboxing (Pyblish/subprocess) and API-token hashing remain open enhancements outside the audit-remediation scope.
