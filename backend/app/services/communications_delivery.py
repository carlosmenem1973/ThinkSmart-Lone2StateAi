"""Provider adapters for audited outbound communications."""
from __future__ import annotations

import re

import boto3
import httpx

from app.core.config import settings


class DeliveryError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _normalise_whatsapp_number(value: str) -> str:
    digits = re.sub(r"\D", "", value or "")
    if digits.startswith("00"):
        digits = digits[2:]
    if not digits or len(digits) < 8:
        raise DeliveryError("invalid_recipient_phone")
    return digits


def send_whatsapp_text(destination: str, body: str) -> str:
    token = settings.meta_whatsapp_access_token
    phone_number_id = settings.meta_whatsapp_phone_number_id
    if not token or not phone_number_id:
        raise DeliveryError("whatsapp_provider_not_configured")
    url = f"https://graph.facebook.com/{settings.meta_graph_api_version}/{phone_number_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": _normalise_whatsapp_number(destination),
        "type": "text",
        "text": {"preview_url": False, "body": body},
    }
    try:
        response = httpx.post(
            url,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=payload,
            timeout=20.0,
        )
        response.raise_for_status()
        data = response.json()
    except httpx.HTTPStatusError as exc:
        try:
            error = exc.response.json().get("error", {})
            code = f"meta_{error.get('code', exc.response.status_code)}"
        except Exception:
            code = f"meta_http_{exc.response.status_code}"
        raise DeliveryError(code) from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise DeliveryError("meta_transport_or_response_error") from exc
    messages = data.get("messages") or []
    provider_id = messages[0].get("id") if messages else None
    if not provider_id:
        raise DeliveryError("meta_missing_message_id")
    return str(provider_id)


def send_email_ses(destination: str, subject: str, body: str) -> str:
    sender = (settings.email_from_address or "").strip()
    if not sender or not settings.ses_sender_verified:
        raise DeliveryError("ses_sender_identity_not_verified")
    try:
        client = boto3.client("sesv2", region_name=settings.aws_region)
        response = client.send_email(
            FromEmailAddress=sender,
            Destination={"ToAddresses": [destination]},
            Content={
                "Simple": {
                    "Subject": {"Data": subject[:998], "Charset": "UTF-8"},
                    "Body": {"Text": {"Data": body, "Charset": "UTF-8"}},
                }
            },
        )
    except Exception as exc:
        # Do not expose provider response bodies, credentials or recipient data.
        response = getattr(exc, "response", {}) or {}
        error = (response.get("Error") or {}).get("Code") or "ses_send_failed"
        raise DeliveryError(f"ses_{str(error)[:80]}") from exc
    message_id = response.get("MessageId")
    if not message_id:
        raise DeliveryError("ses_missing_message_id")
    return str(message_id)
