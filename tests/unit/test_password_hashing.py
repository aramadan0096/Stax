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
