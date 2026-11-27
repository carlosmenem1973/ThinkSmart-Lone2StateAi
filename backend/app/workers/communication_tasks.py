"""Durable SQS relay and outbound communications consumer.

The database outbox is committed with the approval state. SQS carries only the
message ID; message content and recipient data remain in PostgreSQL.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import boto3
from sqlalchemy import select

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.communications import (
    CommunicationChannel,
    CommunicationMessage,
    CommunicationOutbox,
    CommunicationThread,
    ContactChannelConsent,
)
from app.models.contact import Contact
from app.models.entities import AuditLog
from app.services.communications_delivery import (
    DeliveryError,
    send_email_ses,
    send_email_microsoft_graph,
    send_whatsapp_text,
)
from app.workers.celery_app import celery


def _sqs_client():
    return boto3.client("sqs", region_name=settings.aws_region)


@celery.task(name="app.workers.communication_tasks.publish_pending_outbox")
def publish_pending_outbox():
    """Publish committed outbox IDs to SQS; repeated publication is idempotent."""
    queue_url = settings.communications_sqs_queue_url
    if not queue_url:
        return {"status": "queue_not_configured", "published": 0}

    published = 0
    now = datetime.now(timezone.utc)
    for _ in range(25):
        db = SessionLocal()
        try:
            row = db.scalar(
                select(CommunicationOutbox)
                .where(
                    CommunicationOutbox.status == "pending",
                    CommunicationOutbox.available_at <= now,
                )
                .order_by(CommunicationOutbox.id)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if row is None:
                db.rollback()
                break
            message_id = row.message_id
            message = db.get(CommunicationMessage, message_id)
            if message is None:
                row.status = "failed"
                row.last_error = "message_not_found"
                db.commit()
                continue
            try:
                _sqs_client().send_message(
                    QueueUrl=queue_url,
                    MessageBody=json.dumps({"message_id": message_id}),
                    MessageGroupId=str(message.thread_id),
                    MessageDeduplicationId=f"communication-{message_id}",
                )
            except Exception as exc:
                row.attempts += 1
                row.last_error = type(exc).__name__[:100]
                row.available_at = now + timedelta(seconds=min(300, 2 ** min(row.attempts, 8)))
                db.commit()
                break
            # If this commit fails after SQS accepted the event, the row remains
            # pending and may be published again. The consumer deduplicates by DB state.
            row.status = "published"
            row.published_at = now
            row.attempts += 1
            row.last_error = None
            db.commit()
            published += 1
        finally:
            db.close()
    return {"status": "completed", "published": published}


def _delete_sqs_message(receipt_handle: str) -> None:
    _sqs_client().delete_message(
        QueueUrl=settings.communications_sqs_queue_url,
        ReceiptHandle=receipt_handle,
    )


def _consent_is_valid(db, contact, channel_name: str, purpose: str, now: datetime) -> bool:
    if not contact.active or contact.do_not_contact or not contact.contact_permission:
        return False
    consent = db.scalar(
        select(ContactChannelConsent).where(
            ContactChannelConsent.contact_id == contact.id,
            ContactChannelConsent.channel == channel_name,
            ContactChannelConsent.purpose == purpose,
        )
    )
    if purpose == "marketing" and (not consent or consent.status != "granted"):
        return False
    if consent and (
        consent.status in {"denied", "withdrawn"}
        or (consent.expires_at and consent.expires_at <= now)
    ):
        return False
    return True


def _process_sqs_record(record: dict) -> str:
    receipt = record["ReceiptHandle"]
    try:
        message_id = int(json.loads(record["Body"])["message_id"])
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        _delete_sqs_message(receipt)
        return "invalid"

    db = SessionLocal()
    try:
        message = db.scalar(
            select(CommunicationMessage)
            .where(CommunicationMessage.id == message_id)
            .with_for_update()
        )
        outbox = db.scalar(
            select(CommunicationOutbox)
            .where(CommunicationOutbox.message_id == message_id)
            .with_for_update()
        )
        if not message or not outbox:
            db.rollback()
            _delete_sqs_message(receipt)
            return "missing"

        if message.status in {"sent", "failed", "delivery_uncertain"}:
            db.rollback()
            _delete_sqs_message(receipt)
            return "already_final"
        if message.status == "sending":
            # A prior consumer may have crashed after provider acceptance. Never resend blindly.
            message.status = "delivery_uncertain"
            message.error_code = "delivery_outcome_uncertain"
            outbox.status = "uncertain"
            db.add(AuditLog(
                action="communications.message_delivery_uncertain",
                entity_type="communication_message",
                entity_id=str(message.id),
                details={"reason": "redelivered_while_sending"},
            ))
            db.commit()
            _delete_sqs_message(receipt)
            return "uncertain"
        if message.status != "queued":
            db.rollback()
            _delete_sqs_message(receipt)
            return "not_queued"

        thread = db.get(CommunicationThread, message.thread_id)
        contact = db.get(Contact, thread.contact_id) if thread and thread.contact_id else None
        if not thread or not contact:
            message.status = "failed"
            message.error_code = "missing_crm_contact"
            outbox.status = "failed"
            db.commit()
            _delete_sqs_message(receipt)
            return "failed"

        purpose = str((message.metadata_json or {}).get("purpose") or "service")
        now = datetime.now(timezone.utc)
        channel = db.scalar(
            select(CommunicationChannel).where(
                CommunicationChannel.channel == thread.channel,
                CommunicationChannel.provider.in_({"meta_whatsapp_cloud"} if thread.channel == "whatsapp" else {"aws_ses", "microsoft_graph"}),
                CommunicationChannel.enabled.is_(True),
                CommunicationChannel.outbound_enabled.is_(True),
            ).order_by(CommunicationChannel.id.desc())
        )
        destination = contact.phone if thread.channel == "whatsapp" else contact.email
        if (
            not channel
            or not destination
            or not _consent_is_valid(db, contact, thread.channel, purpose, now)
        ):
            message.status = "failed"
            message.error_code = "channel_or_consent_revalidation_failed"
            outbox.status = "failed"
            db.add(AuditLog(
                action="communications.message_send_blocked",
                entity_type="communication_message",
                entity_id=str(message.id),
                details={"reason": message.error_code},
            ))
            db.commit()
            _delete_sqs_message(receipt)
            return "blocked"

        if thread.channel == "whatsapp":
            last_inbound = db.scalar(
                select(CommunicationMessage)
                .where(
                    CommunicationMessage.thread_id == thread.id,
                    CommunicationMessage.direction == "inbound",
                )
                .order_by(CommunicationMessage.created_at.desc())
                .limit(1)
            )
            inbound_at = last_inbound.created_at if last_inbound else None
            if inbound_at and inbound_at.tzinfo is None:
                inbound_at = inbound_at.replace(tzinfo=timezone.utc)
            if not inbound_at or (now - inbound_at).total_seconds() >= 86400:
                message.status = "failed"
                message.error_code = "whatsapp_service_window_closed"
                outbox.status = "failed"
                db.commit()
                _delete_sqs_message(receipt)
                return "blocked"

        message.status = "sending"
        message.metadata_json = {
            **(message.metadata_json or {}),
            "provider": channel.provider,
            "delivery_started": True,
        }
        outbox.status = "processing"
        db.commit()

        try:
            if thread.channel == "whatsapp":
                provider_message_id = send_whatsapp_text(str(destination), message.body)
            elif thread.channel == "email" and channel.provider == "aws_ses":
                provider_message_id = send_email_ses(
                    str(destination), thread.subject or "Mensagem ThinkSmart AI", message.body,
                )
            elif thread.channel == "email" and channel.provider == "microsoft_graph":
                provider_message_id = send_email_microsoft_graph(
                    str(destination), thread.subject or "Mensagem ThinkSmart AI", message.body,
                )
            else:
                raise DeliveryError("unsupported_outbound_channel")
        except DeliveryError as exc:
            final_status = "delivery_uncertain" if exc.ambiguous else "failed"
            message.status = final_status
            message.error_code = exc.code[:100]
            outbox.status = "uncertain" if exc.ambiguous else "failed"
            outbox.last_error = exc.code[:100]
            db.add(AuditLog(
                action=(
                    "communications.message_delivery_uncertain"
                    if exc.ambiguous
                    else "communications.message_send_failed"
                ),
                entity_type="communication_message",
                entity_id=str(message.id),
                details={
                    "channel": thread.channel,
                    "provider": channel.provider,
                    "error_code": exc.code[:100],
                },
            ))
            db.commit()
            _delete_sqs_message(receipt)
            return "uncertain" if exc.ambiguous else "failed"
        except Exception:
            message.status = "delivery_uncertain"
            message.error_code = "provider_outcome_uncertain"
            outbox.status = "uncertain"
            outbox.last_error = "provider_outcome_uncertain"
            db.add(AuditLog(
                action="communications.message_delivery_uncertain",
                entity_type="communication_message",
                entity_id=str(message.id),
                details={"channel": thread.channel, "provider": channel.provider},
            ))
            db.commit()
            _delete_sqs_message(receipt)
            return "uncertain"

        message.status = "sent"
        message.provider_message_id = provider_message_id
        message.sent_at = datetime.now(timezone.utc)
        outbox.status = "completed"
        db.add(AuditLog(
            action="communications.message_sent",
            entity_type="communication_message",
            entity_id=str(message.id),
            details={
                "channel": thread.channel,
                "provider": channel.provider,
                "provider_message_id": provider_message_id,
            },
        ))
        db.commit()
        _delete_sqs_message(receipt)
        return "sent"
    finally:
        db.close()


@celery.task(name="app.workers.communication_tasks.consume_sqs_messages")
def consume_sqs_messages():
    """Consume a bounded batch; SQS visibility and DB state prevent blind retries."""
    if not settings.communications_sqs_queue_url:
        return {"status": "queue_not_configured", "processed": 0}
    response = _sqs_client().receive_message(
        QueueUrl=settings.communications_sqs_queue_url,
        MaxNumberOfMessages=1,
        WaitTimeSeconds=0,
        VisibilityTimeout=120,
    )
    counts = {}
    for record in response.get("Messages", []):
        result = _process_sqs_record(record)
        counts[result] = counts.get(result, 0) + 1
    return {"status": "completed", "processed": sum(counts.values()), "results": counts}
