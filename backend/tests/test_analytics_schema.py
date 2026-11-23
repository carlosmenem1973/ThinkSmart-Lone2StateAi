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
