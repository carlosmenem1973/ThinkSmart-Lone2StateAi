from app.core.config import settings
from app.services import communications_delivery as delivery


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_whatsapp_text_uses_meta_cloud_api_and_normalizes_portuguese_phone(monkeypatch):
    captured = {}
    monkeypatch.setattr(settings, "meta_whatsapp_access_token", "test-token")
    monkeypatch.setattr(settings, "meta_whatsapp_phone_number_id", "123456789")
    monkeypatch.setattr(settings, "meta_graph_api_version", "v26.0")

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return FakeResponse({"messages": [{"id": "wamid.test-message"}]})

    monkeypatch.setattr(delivery.httpx, "post", fake_post)
    result = delivery.send_whatsapp_text("+351 912 345 678", "Olá")

    assert result == "wamid.test-message"
    assert captured["url"].endswith("/v26.0/123456789/messages")
    assert captured["json"]["to"] == "351912345678"
    assert captured["json"]["text"]["body"] == "Olá"
    assert captured["headers"]["Authorization"] == "Bearer test-token"


def test_ses_email_uses_configured_sender_and_returns_provider_id(monkeypatch):
    captured = {}
    monkeypatch.setattr(settings, "email_from_address", "contacto@cbloft2.pt")
    monkeypatch.setattr(settings, "ses_sender_verified", True)

    class FakeSes:
        def send_email(self, **kwargs):
            captured.update(kwargs)
            return {"MessageId": "ses-message-123"}

    monkeypatch.setattr(delivery.boto3, "client", lambda *args, **kwargs: FakeSes())
    result = delivery.send_email_ses("cliente@example.com", "Imóvel disponível", "Bom dia")

    assert result == "ses-message-123"
    assert captured["FromEmailAddress"] == "contacto@cbloft2.pt"
    assert captured["Destination"]["ToAddresses"] == ["cliente@example.com"]
    assert captured["Content"]["Simple"]["Subject"]["Data"] == "Imóvel disponível"


def test_ses_email_refuses_unverified_sender(monkeypatch):
    monkeypatch.setattr(settings, "email_from_address", "contacto@cbloft2.pt")
    monkeypatch.setattr(settings, "ses_sender_verified", False)
    try:
        delivery.send_email_ses("cliente@example.com", "Assunto", "Texto")
    except delivery.DeliveryError as exc:
        assert exc.code == "ses_sender_identity_not_verified"
    else:
        raise AssertionError("Unverified SES sender must be rejected")


def test_delivery_error_exposes_ambiguous_outcome_for_manual_reconciliation():
    ambiguous = delivery.DeliveryError("provider_timeout", ambiguous=True)
    definitive = delivery.DeliveryError("invalid_recipient")

    assert ambiguous.ambiguous is True
    assert definitive.ambiguous is False
