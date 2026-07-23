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
