"""Authenticated API for centralized omnichannel communications.

This increment creates auditable drafts and consent records. It does not transmit
messages until provider send adapters and verified webhooks are configured.
"""
from datetime import datetime, timezone
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.core.auth import get_business_user, require_admin_user
from app.core.database import get_db
from app.models.contact import Contact
from app.models.entities import AuditLog, User, UserRole
from app.models.communications import CommunicationChannel, CommunicationMessage, CommunicationThread, ContactChannelConsent
from app.core.config import settings

router = APIRouter(prefix="/communications", tags=["Communications"])
CHANNELS = {"whatsapp", "sms", "email"}
PROVIDERS = {"meta_whatsapp_cloud", "aws_end_user_messaging", "microsoft_graph"}

class ConsentInput(BaseModel):
    channel: Literal["whatsapp", "sms", "email"]
    purpose: Literal["service", "property_enquiry", "marketing", "transactional"]
    status: Literal["granted", "denied", "withdrawn", "unknown"]
    lawful_basis: str | None = Field(default=None, max_length=80)
    evidence_source: str | None = Field(default=None, max_length=500)
    evidence_reference: str | None = Field(default=None, max_length=1000)
    expires_at: datetime | None = None

class InboundChannelInput(BaseModel):
    phone_number_id: str = Field(min_length=5, max_length=100)
    enabled: bool = True

class DraftInput(BaseModel):
    contact_id: int
    channel: Literal["whatsapp", "sms", "email"]
    body: str = Field(min_length=1, max_length=10000)
    purpose: Literal["service", "property_enquiry", "marketing", "transactional"] = "service"
    subject: str | None = Field(default=None, max_length=998)

def _can_access_contact(user: User, contact: Contact):
    if user.role in {UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.MANAGER}:
        return
    if contact.assigned_to != user.id and contact.created_by != user.id:
        raise HTTPException(status_code=404, detail="Contact not found")

def _consent_for(db: Session, contact_id: int, channel: str, purpose: str):
    return db.scalar(select(ContactChannelConsent).where(
        ContactChannelConsent.contact_id == contact_id,
        ContactChannelConsent.channel == channel,
        ContactChannelConsent.purpose == purpose,
    ))

@router.get("/overview")
def communications_overview(user: User = Depends(get_business_user), db: Session = Depends(get_db)):
    if user.role == UserRole.VIEWER:
        raise HTTPException(status_code=403, detail="Viewer accounts cannot access communications")
    channels = db.scalars(select(CommunicationChannel).order_by(CommunicationChannel.channel)).all()
    counts = {}
    for status in ("draft", "pending_approval", "approved", "sent", "failed"):
        counts[status] = len(db.scalars(select(CommunicationMessage).where(CommunicationMessage.status == status).limit(500)).all())
    return {
        "account_scope": "central", "autonomy_mode": "hybrid", "voice_enabled": False,
        "channels": [{"id": c.id, "channel": c.channel, "provider": c.provider,
            "display_name": c.display_name, "sender_identifier": c.sender_identifier,
            "enabled": c.enabled, "inbound_enabled": c.inbound_enabled,
            "outbound_enabled": c.outbound_enabled,
            "ready": bool(c.enabled and (c.inbound_enabled or c.outbound_enabled))} for c in channels],
        "message_counts": counts, "sending_enabled": False,
        "note": "Provider delivery remains disabled until credentials, sender verification and webhook validation are configured.",
    }

@router.post("/channels", status_code=201)
def register_channel(payload: dict, admin: User = Depends(require_admin_user), db: Session = Depends(get_db)):
    channel = str(payload.get("channel", "")).lower()
    provider = str(payload.get("provider", "")).lower()
    display_name = str(payload.get("display_name", "")).strip()
    if channel not in CHANNELS:
        raise HTTPException(status_code=422, detail="Unsupported channel")
    if provider not in PROVIDERS:
        raise HTTPException(status_code=422, detail="Unsupported provider")
    expected = {"whatsapp": "meta_whatsapp_cloud", "sms": "aws_end_user_messaging", "email": "microsoft_graph"}
    if expected[channel] != provider:
        raise HTTPException(status_code=422, detail="Provider does not match channel")
    if not display_name:
        raise HTTPException(status_code=422, detail="display_name is required")
    row = CommunicationChannel(channel=channel, provider=provider, account_scope="central",
        display_name=display_name, sender_identifier=payload.get("sender_identifier"),
        enabled=False, inbound_enabled=False, outbound_enabled=False, configuration_json={})
    db.add(row)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Channel already registered")
    db.add(AuditLog(actor_id=admin.id, action="communications.channel_registered",
        entity_type="communication_channel", entity_id=str(row.id),
        details={"channel": channel, "provider": provider, "account_scope": "central"}))
    db.commit()
    return {"id": row.id, "channel": row.channel, "provider": row.provider, "enabled": False, "ready": False}

@router.put("/channels/{channel_id}/inbound")
def configure_whatsapp_inbound(
    channel_id: int,
    payload: InboundChannelInput,
    admin: User = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    row = db.get(CommunicationChannel, channel_id)
    if not row or row.channel != "whatsapp" or row.provider != "meta_whatsapp_cloud":
        raise HTTPException(status_code=404, detail="Meta WhatsApp channel not found")
    if payload.enabled and (not settings.meta_whatsapp_app_secret or not settings.meta_whatsapp_verify_token):
        raise HTTPException(status_code=503, detail="Configure META_WHATSAPP_APP_SECRET and META_WHATSAPP_VERIFY_TOKEN in AWS Secrets Manager first")
    row.configuration_json = {**(row.configuration_json or {}), "phone_number_id": payload.phone_number_id}
    row.enabled = payload.enabled
    row.inbound_enabled = payload.enabled
    # Outbound stays disabled until a separate send adapter and approval workflow are deployed.
    row.outbound_enabled = False
    db.add(AuditLog(actor_id=admin.id, action="communications.whatsapp_inbound_configured",
        entity_type="communication_channel", entity_id=str(row.id),
        details={"enabled": payload.enabled, "phone_number_id": payload.phone_number_id}))
    db.commit()
    return {"id": row.id, "channel": row.channel, "enabled": row.enabled,
        "inbound_enabled": row.inbound_enabled, "outbound_enabled": row.outbound_enabled}


@router.put("/contacts/{contact_id}/consent")
def upsert_contact_consent(contact_id: int, payload: ConsentInput,
    user: User = Depends(get_business_user), db: Session = Depends(get_db)):
    contact = db.get(Contact, contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    _can_access_contact(user, contact)
    row = _consent_for(db, contact_id, payload.channel, payload.purpose)
    now = datetime.now(timezone.utc)
    if row is None:
        row = ContactChannelConsent(contact_id=contact_id, channel=payload.channel, purpose=payload.purpose)
        db.add(row)
    row.status = payload.status
    row.lawful_basis = payload.lawful_basis
    row.evidence_source = payload.evidence_source
    row.evidence_reference = payload.evidence_reference
    row.expires_at = payload.expires_at
    row.captured_at = now if payload.status == "granted" else row.captured_at
    row.captured_by = user.id
    row.revoked_at = now if payload.status in {"withdrawn", "denied"} else None
    # Channel-specific withdrawal is recorded here; the CRM-wide do_not_contact
    # flag remains a separate global suppression control.
    db.add(AuditLog(actor_id=user.id, action="communications.consent_updated",
        entity_type="contact", entity_id=str(contact_id),
        details={"channel": payload.channel, "purpose": payload.purpose, "status": payload.status}))
    db.commit()
    return {"contact_id": contact_id, "channel": row.channel, "purpose": row.purpose,
        "status": row.status, "do_not_contact": contact.do_not_contact}

@router.get("/contacts/{contact_id}/consent")
def list_contact_consents(contact_id: int, user: User = Depends(get_business_user), db: Session = Depends(get_db)):
    contact = db.get(Contact, contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    _can_access_contact(user, contact)
    rows = db.scalars(select(ContactChannelConsent).where(ContactChannelConsent.contact_id == contact_id)
        .order_by(ContactChannelConsent.channel, ContactChannelConsent.purpose)).all()
    return [{"id": r.id, "channel": r.channel, "purpose": r.purpose, "status": r.status,
        "lawful_basis": r.lawful_basis, "evidence_source": r.evidence_source,
        "evidence_reference": r.evidence_reference, "captured_at": r.captured_at,
        "expires_at": r.expires_at, "revoked_at": r.revoked_at} for r in rows]

@router.post("/drafts", status_code=201)
def create_message_draft(payload: DraftInput, user: User = Depends(get_business_user), db: Session = Depends(get_db)):
    contact = db.get(Contact, payload.contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    _can_access_contact(user, contact)
    if contact.do_not_contact:
        raise HTTPException(status_code=409, detail="Contact is globally suppressed (do_not_contact)")
    destination = contact.phone if payload.channel in {"whatsapp", "sms"} else contact.email
    if not destination:
        raise HTTPException(status_code=422, detail=f"Contact has no destination for {payload.channel}")
    consent = _consent_for(db, contact.id, payload.channel, payload.purpose)
    now = datetime.now(timezone.utc)
    if payload.purpose == "marketing" and (not consent or consent.status != "granted" or (consent.expires_at and consent.expires_at <= now)):
        raise HTTPException(status_code=403, detail="Valid channel-specific marketing consent is required")
    if consent and consent.status in {"denied", "withdrawn"}:
        raise HTTPException(status_code=403, detail="Contact has withdrawn or denied this channel/purpose")
    thread = db.scalar(select(CommunicationThread).where(
        CommunicationThread.contact_id == contact.id, CommunicationThread.channel == payload.channel,
        CommunicationThread.status == "open").order_by(desc(CommunicationThread.last_message_at)))
    if thread is None:
        thread = CommunicationThread(contact_id=contact.id, channel=payload.channel, subject=payload.subject, assigned_to=user.id)
        db.add(thread)
        db.flush()
    message = CommunicationMessage(thread_id=thread.id, direction="outbound", actor_type="human",
        actor_id=user.id, body=payload.body, status="pending_approval", requires_approval=True,
        metadata_json={"purpose": payload.purpose, "destination_masked": destination[:3] + "***"})
    db.add(message)
    thread.last_message_at = now
    db.add(AuditLog(actor_id=user.id, action="communications.message_drafted",
        entity_type="communication_message", entity_id="pending",
        details={"contact_id": contact.id, "channel": payload.channel, "purpose": payload.purpose}))
    db.commit()
    db.refresh(message)
    return {"message_id": message.id, "thread_id": thread.id, "status": message.status,
        "requires_approval": True, "sent": False, "note": "Draft saved. No message has been sent."}

@router.get("/inbox")
def list_inbox(user: User = Depends(get_business_user), db: Session = Depends(get_db)):
    if user.role == UserRole.VIEWER:
        raise HTTPException(status_code=403, detail="Viewer accounts cannot access communications")
    query = select(CommunicationThread).order_by(desc(CommunicationThread.last_message_at)).limit(100)
    if user.role == UserRole.SELLER:
        query = select(CommunicationThread).where(CommunicationThread.assigned_to == user.id).order_by(desc(CommunicationThread.last_message_at)).limit(100)
    rows = db.scalars(query).all()
    output = []
    for thread in rows:
        contact = db.get(Contact, thread.contact_id) if thread.contact_id else None
        last = db.scalar(select(CommunicationMessage).where(CommunicationMessage.thread_id == thread.id)
            .order_by(desc(CommunicationMessage.created_at)).limit(1))
        output.append({"id": thread.id, "contact_id": thread.contact_id,
            "contact_name": contact.full_name if contact else None,
            "contact_type": contact.contact_type if contact else None,
            "channel": thread.channel, "subject": thread.subject, "status": thread.status,
            "last_message_at": thread.last_message_at,
            "last_message": last.body[:240] if last else None,
            "last_message_status": last.status if last else None})
    return output

@router.get("/inbox/{thread_id}/messages")
def list_thread_messages(thread_id: int, user: User = Depends(get_business_user), db: Session = Depends(get_db)):
    thread = db.get(CommunicationThread, thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    if user.role == UserRole.SELLER and thread.assigned_to != user.id:
        raise HTTPException(status_code=404, detail="Thread not found")
    rows = db.scalars(select(CommunicationMessage).where(CommunicationMessage.thread_id == thread_id)
        .order_by(CommunicationMessage.created_at)).all()
    return [{"id": m.id, "direction": m.direction, "actor_type": m.actor_type, "body": m.body,
        "status": m.status, "requires_approval": m.requires_approval, "approved_by": m.approved_by,
        "approved_at": m.approved_at, "sent_at": m.sent_at, "created_at": m.created_at} for m in rows]

@router.get("/drafts/pending")
def list_pending_message_drafts(user: User = Depends(get_business_user), db: Session = Depends(get_db)):
    """List pending human-approval drafts visible to the authenticated user."""
    if user.role == UserRole.VIEWER:
        raise HTTPException(status_code=403, detail="Viewer accounts cannot access communications")
    query = (
        select(CommunicationMessage, CommunicationThread, Contact)
        .join(CommunicationThread, CommunicationMessage.thread_id == CommunicationThread.id)
        .outerjoin(Contact, CommunicationThread.contact_id == Contact.id)
        .where(CommunicationMessage.status == "pending_approval")
        .order_by(desc(CommunicationMessage.created_at))
        .limit(100)
    )
    if user.role == UserRole.SELLER:
        query = query.where(CommunicationThread.assigned_to == user.id)
    rows = db.execute(query).all()
    return [{
        "message_id": message.id,
        "thread_id": thread.id,
        "contact_id": thread.contact_id,
        "contact_name": contact.full_name if contact else None,
        "channel": thread.channel,
        "subject": thread.subject,
        "body": message.body,
        "created_at": message.created_at,
        "requires_approval": message.requires_approval,
    } for message, thread, contact in rows]


@router.post("/drafts/{message_id}/approve")
def approve_message_draft(message_id: int, admin: User = Depends(require_admin_user), db: Session = Depends(get_db)):
    message = db.get(CommunicationMessage, message_id)
    if not message or message.status != "pending_approval":
        raise HTTPException(status_code=404, detail="Pending draft not found")
    message.status = "approved"
    message.approved_by = admin.id
    message.approved_at = datetime.now(timezone.utc)
    db.add(AuditLog(actor_id=admin.id, action="communications.message_approved",
        entity_type="communication_message", entity_id=str(message.id), details={"delivery_started": False}))
    db.commit()
    return {"message_id": message.id, "status": "approved", "sent": False,
        "note": "Approved and audited; provider delivery is not enabled yet."}
