import pytest
from pydantic import ValidationError
from app.api.analytics import UsageEventInput

def test_accepts_valid_usage_event():
    event = UsageEventInput(event_type="page_view", feature="procura", route="/research", session_id="session_123456")
    assert event.feature == "procura"

@pytest.mark.parametrize("feature", ["admin", "billing", "users"])
def test_rejects_unknown_feature(feature):
    with pytest.raises(ValidationError):
        UsageEventInput(event_type="page_view", feature=feature, session_id="session_123456")

def test_rejects_extra_personal_data_fields():
    with pytest.raises(ValidationError):
        UsageEventInput(event_type="feature_action", feature="agents", session_id="session_123456", email="person@example.pt")

from fastapi import HTTPException
from app.core.auth import CognitoPrincipal, require_admin
from app.models.entities import UserRole

def test_admin_can_read_analytics():
    principal = CognitoPrincipal(sub="sub-admin", email="admin@example.pt", username="admin", name="Admin", groups=frozenset({"ADMIN"}), role=UserRole.ADMIN)
    assert require_admin(principal) == principal

def test_seller_cannot_read_admin_analytics():
    principal = CognitoPrincipal(sub="sub-seller", email="seller@example.pt", username="seller", name="Seller", groups=frozenset({"SELLER"}), role=UserRole.SELLER)
    with pytest.raises(HTTPException) as error:
        require_admin(principal)
    assert error.value.status_code == 403
