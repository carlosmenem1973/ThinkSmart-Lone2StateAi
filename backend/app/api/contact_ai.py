from datetime import datetime, timedelta, timezone
from pydantic import BaseModel, Field, EmailStr
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, desc
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.auth import get_business_user, require_admin_user
from app.models.entities import User, UserRole, AuditLog
from app.models.contact_ai import ContactAISettings, ContactConversation, ContactMessage
from app.services.ai import bedrock_generate, AIUnavailable

router = APIRouter(prefix="/contact-ai", tags=["Contact AI"])

class ChatInput(BaseModel):
    visitor_id: str = Field(min_length=8, max_length=80)
    message: str = Field(min_length=1, max_length=4000)
    name: str | None = Field(default=None, max_length=160)
    email: EmailStr | None = None
    consent_to_followup: bool = False

class SettingsInput(BaseModel):
    enabled: bool
    mode: str = Field(pattern="^(approval|autonomous)$")
    interval_minutes: int = Field(default=30, ge=30, le=1440)

def _settings(db: Session):
    row = db.get(ContactAISettings, 1)
    if row is None:
        row = ContactAISettings(id=1, enabled=False, mode="approval", interval_minutes=30, channel="website")
        db.add(row)
        db.commit()
        db.refresh(row)
    return row

def _reply(history: list[ContactMessage], incoming: str) -> str:
    transcript = "\n".join(f"{m.role}: {m.content[:2000]}" for m in history[-12:])
    return bedrock_generate(
        "És o assistente virtual do ThinkSmart AI / Loft2 Real Estate em Portugal. Responde em português europeu, com clareza e cordialidade. Ajuda com dúvidas imobiliárias e recolhe apenas os dados estritamente necessários. Nunca inventes imóveis, preços, disponibilidade ou condições. Não peças dados sensíveis, não prometas resultados e não afirmes que és humano. Se não souberes, encaminha para a equipa. Não peças consentimento presumido.",
        f"Histórico da conversa:\n{transcript}\n\nNova mensagem do visitante:\n{incoming}",
        max_tokens=700, temperature=0.25,
    )

@router.post("/chat")
def website_chat(payload: ChatInput, db: Session = Depends(get_db)):
    """Public website chat. A conversation is only linked to follow-up when explicit consent is supplied."""
    row = db.scalar(select(ContactConversation).where(ContactConversation.visitor_id == payload.visitor_id, ContactConversation.status == "open"))
    if row is None:
        row = ContactConversation(visitor_id=payload.visitor_id)
        db.add(row)
        db.flush()
    if payload.name:
        row.visitor_name = payload.name
    if payload.email:
        row.visitor_email = str(payload.email)
    row.consent_to_followup = bool(row.consent_to_followup or payload.consent_to_followup)
    row.last_message_at = datetime.now(timezone.utc)
    db.add(ContactMessage(conversation_id=row.id, role="visitor", content=payload.message, delivery_status="received"))
    db.flush()
    config = _settings(db)
    history = db.scalars(select(ContactMessage).where(ContactMessage.conversation_id == row.id).order_by(ContactMessage.created_at)).all()
    # The website chatbot answers interactively when Contact AI is enabled. In approval mode,
    # it still answers website questions; outbound follow-up remains a human-approved draft.
    if not config.enabled:
        answer = "Obrigado pela sua mensagem. A equipa ThinkSmart AI irá analisar o seu pedido."
        delivery_status = "delivered"
    elif config.mode == "approval":
        try:
            suggestion = _reply(history, payload.message)
        except AIUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        db.add(ContactMessage(conversation_id=row.id, role="assistant", content=suggestion, delivery_status="draft"))
        answer = "Obrigado pelo seu contacto. Registámos a sua mensagem e a nossa equipa irá responder assim que possível."
        delivery_status = "delivered"
    else:
        try:
            answer = _reply(history, payload.message)
        except AIUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        delivery_status = "delivered"
    db.add(ContactMessage(conversation_id=row.id, role="assistant", content=answer, delivery_status=delivery_status))
    db.commit()
    return {"conversation_id": row.id, "reply": answer, "mode": config.mode if config.enabled else "disabled"}

@router.get("/settings")
def get_settings(_admin: User = Depends(require_admin_user), db: Session = Depends(get_db)):
    row = _settings(db)
    return {"enabled": row.enabled, "mode": row.mode, "interval_minutes": row.interval_minutes, "channel": row.channel, "paused": bool(row.paused_until and row.paused_until > datetime.now(timezone.utc)), "updated_at": row.updated_at}

@router.put("/settings")
def update_settings(payload: SettingsInput, admin: User = Depends(require_admin_user), db: Session = Depends(get_db)):
    row = _settings(db)
    row.enabled = payload.enabled
    row.mode = payload.mode
    row.interval_minutes = payload.interval_minutes
    row.paused_until = None
    row.updated_by = admin.id
    db.add(AuditLog(actor_id=admin.id, action="contact_ai.settings_updated", entity_type="contact_ai", entity_id="1", details=payload.model_dump()))
    db.commit()
    return {"enabled": row.enabled, "mode": row.mode, "interval_minutes": row.interval_minutes, "channel": row.channel}

@router.post("/pause")
def pause_agent(admin: User = Depends(require_admin_user), db: Session = Depends(get_db)):
    row = _settings(db)
    row.paused_until = datetime.now(timezone.utc) + timedelta(days=3650)
    row.updated_by = admin.id
    db.add(AuditLog(actor_id=admin.id, action="contact_ai.paused", entity_type="contact_ai", entity_id="1", details={}))
    db.commit()
    return {"paused": True}

@router.post("/resume")
def resume_agent(admin: User = Depends(require_admin_user), db: Session = Depends(get_db)):
    row = _settings(db)
    row.paused_until = None
    row.updated_by = admin.id
    db.add(AuditLog(actor_id=admin.id, action="contact_ai.resumed", entity_type="contact_ai", entity_id="1", details={}))
    db.commit()
    return {"paused": False}

@router.delete("/configuration")
def remove_configuration(admin: User = Depends(require_admin_user), db: Session = Depends(get_db)):
    row = db.get(ContactAISettings, 1)
    if row:
        db.delete(row)
    db.add(AuditLog(actor_id=admin.id, action="contact_ai.configuration_removed", entity_type="contact_ai", entity_id="1", details={}))
    db.commit()
    return {"removed": True, "enabled": False}

@router.get("/conversations")
def list_conversations(user: User = Depends(get_business_user), db: Session = Depends(get_db)):
    if user.role == UserRole.VIEWER:
        raise HTTPException(status_code=403, detail="Viewer accounts cannot access contact conversations")
    rows = db.scalars(select(ContactConversation).order_by(desc(ContactConversation.last_message_at)).limit(100)).all()
    return [{"id": x.id, "name": x.visitor_name, "email": x.visitor_email, "consent_to_followup": x.consent_to_followup, "status": x.status, "last_message_at": x.last_message_at} for x in rows]

@router.get("/conversations/{conversation_id}/messages")
def list_messages(conversation_id: int, user: User = Depends(get_business_user), db: Session = Depends(get_db)):
    if user.role == UserRole.VIEWER:
        raise HTTPException(status_code=403, detail="Viewer accounts cannot access contact conversations")
    exists = db.get(ContactConversation, conversation_id)
    if not exists:
        raise HTTPException(status_code=404, detail="Conversation not found")
    rows = db.scalars(select(ContactMessage).where(ContactMessage.conversation_id == conversation_id).order_by(ContactMessage.created_at)).all()
    return [{"id": x.id, "role": x.role, "content": x.content, "delivery_status": x.delivery_status, "created_at": x.created_at} for x in rows]
