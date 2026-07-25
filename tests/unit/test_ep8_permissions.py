import pytest
from permissions import (PERMISSIONS, BUILTIN_ROLES,
                         is_valid_permission, default_permissions_for)


@pytest.mark.unit
def test_admin_has_every_permission():
    assert BUILTIN_ROLES["admin"] == set(PERMISSIONS)


@pytest.mark.unit
def test_builtin_roles_only_use_valid_permissions():
    for role, perms in BUILTIN_ROLES.items():
        for p in perms:
            assert is_valid_permission(p), "{} -> bad perm {}".format(role, p)


@pytest.mark.unit
def test_default_permissions_for_known_and_unknown():
    assert default_permissions_for("ingestor") == {"can_ingest"}
    assert default_permissions_for("nope") == set()
