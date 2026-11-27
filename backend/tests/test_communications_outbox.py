from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.core.config import settings
from app.workers import communication_tasks


class FakeDB:
    def __init__(self, result):
        self.result = result

    def scalar(self, _query):
        return self.result


def test_outbox_relay_is_inert_when_queue_is_not_configured(monkeypatch):
    monkeypatch.setattr(settings, "communications_sqs_queue_url", "")
    result = communication_tasks.publish_pending_outbox()
    assert result == {"status": "queue_not_configured", "published": 0}


def test_marketing_delivery_requires_explicit_granted_consent():
    contact = SimpleNamespace(id=12, do_not_contact=False, contact_permission=True)
    db = FakeDB(None)
    assert not communication_tasks._consent_is_valid(
        db, contact, "email", "marketing", datetime.now(timezone.utc)
    )


def test_withdrawn_consent_blocks_service_delivery():
    now = datetime.now(timezone.utc)
    contact = SimpleNamespace(id=12, do_not_contact=False, contact_permission=True)
    consent = SimpleNamespace(status="withdrawn", expires_at=None)
    db = FakeDB(consent)
    assert not communication_tasks._consent_is_valid(db, contact, "whatsapp", "service", now)


def test_expired_consent_blocks_delivery():
    now = datetime.now(timezone.utc)
    contact = SimpleNamespace(id=12, do_not_contact=False, contact_permission=True)
    consent = SimpleNamespace(status="granted", expires_at=now - timedelta(seconds=1))
    db = FakeDB(consent)
    assert not communication_tasks._consent_is_valid(db, contact, "email", "service", now)


def test_global_suppression_blocks_delivery_without_querying_consent():
    contact = SimpleNamespace(id=12, do_not_contact=True, contact_permission=True)
    db = FakeDB(None)
    assert not communication_tasks._consent_is_valid(
        db, contact, "email", "service", datetime.now(timezone.utc)
    )
