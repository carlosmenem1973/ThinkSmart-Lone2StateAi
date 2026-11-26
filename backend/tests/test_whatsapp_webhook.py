import hashlib
import hmac

from app.api.whatsapp_webhook import _normalise_phone, _valid_signature
from app.core.config import settings


def test_whatsapp_signature_accepts_valid_meta_hmac(monkeypatch):
    secret = "test-meta-app-secret"
    body = b'{"object":"whatsapp_business_account"}'
    signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    monkeypatch.setattr(settings, "meta_whatsapp_app_secret", secret)
    assert _valid_signature(body, signature)


def test_whatsapp_signature_rejects_invalid_or_missing_secret(monkeypatch):
    monkeypatch.setattr(settings, "meta_whatsapp_app_secret", "configured-secret")
    assert not _valid_signature(b"{}", "sha256=invalid")
    monkeypatch.setattr(settings, "meta_whatsapp_app_secret", "")
    assert not _valid_signature(b"{}", "sha256=invalid")


def test_whatsapp_phone_normalization_supports_portuguese_csv_prefix():
    assert _normalise_phone("00351 912-345-678") == "351912345678"
    assert _normalise_phone("+351 912 345 678") == "351912345678"
