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
