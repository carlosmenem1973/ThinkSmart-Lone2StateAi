from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.communications import _can_access_thread
from app.models.entities import UserRole


def test_viewer_cannot_read_thread_messages():
    viewer = SimpleNamespace(id=7, role=UserRole.VIEWER)
    thread = SimpleNamespace(id=42, assigned_to=7)

    with pytest.raises(HTTPException) as exc:
        _can_access_thread(viewer, thread)

    assert exc.value.status_code == 403
    assert exc.value.detail == "Viewer accounts cannot access communications"


def test_seller_can_read_only_assigned_thread_messages():
    seller = SimpleNamespace(id=7, role=UserRole.SELLER)
    own_thread = SimpleNamespace(id=42, assigned_to=7)
    other_thread = SimpleNamespace(id=43, assigned_to=8)

    _can_access_thread(seller, own_thread)

    with pytest.raises(HTTPException) as exc:
        _can_access_thread(seller, other_thread)

    assert exc.value.status_code == 404


@pytest.mark.parametrize("role", [UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.MANAGER])
def test_management_roles_can_read_thread_messages(role):
    user = SimpleNamespace(id=7, role=role)
    thread = SimpleNamespace(id=42, assigned_to=8)

    _can_access_thread(user, thread)
