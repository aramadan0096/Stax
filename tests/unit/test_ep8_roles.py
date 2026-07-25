import pytest


@pytest.mark.unit
def test_builtin_roles_seeded(stax_db):
    names = {r["name"] for r in stax_db.get_roles()}
    assert {"admin", "user", "reviewer", "ingestor", "viewer"}.issubset(names)


@pytest.mark.unit
def test_admin_user_has_all_permissions(stax_db):
    # the default admin/admin user is seeded by _create_schema
    assert stax_db.has_permission("admin", "can_delete") is True
    assert stax_db.has_permission("admin", "can_manage_schema") is True


@pytest.mark.unit
def test_role_permission_membership(stax_db):
    stax_db.create_user("rev", "pw", role="reviewer")
    assert stax_db.has_permission("rev", "can_edit_metadata") is True
    assert stax_db.has_permission("rev", "can_delete") is False


@pytest.mark.unit
def test_set_role_permissions_and_custom_role(stax_db):
    rid = stax_db.create_role("editor", permissions={"can_edit_metadata"})
    assert rid > 0
    stax_db.set_role_permissions("editor", {"can_edit_metadata", "can_delete"})
    assert stax_db.get_role_permissions("editor") == {"can_edit_metadata", "can_delete"}


@pytest.mark.unit
def test_delete_role_refuses_builtin(stax_db):
    with pytest.raises(ValueError):
        stax_db.delete_role("admin")


@pytest.mark.unit
def test_unknown_user_or_role_has_no_permission(stax_db):
    assert stax_db.has_permission("ghost", "can_ingest") is False
