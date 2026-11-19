from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from app.workers.celery_app import celery
from app.core.database import SessionLocal
from app.models.contact_ai import ContactAISettings, ContactConversation, ContactMessage
from app.models.entities import AuditLog
from app.services.ai import bedrock_generate, AIUnavailable

@celery.task(name="app.workers.contact_ai_tasks.process_contact_queue")
def process_contact_queue():
    db = SessionLocal()
    try:
        config = db.get(ContactAISettings, 1)
        if not config or not config.enabled:
            return {"status": "disabled"}
        now = datetime.now(timezone.utc)
        if config.paused_until and config.paused_until > now:
            return {"status": "paused"}
        # Website channel has no asynchronous push to an offline browser. Every 30-minute
        # cycle reviews new conversations and creates an internal next-step draft only.
        conversations = db.scalars(
            select(ContactConversation).where(
                ContactConversation.status == "open",
                ContactConversation.last_message_at >= now - timedelta(minutes=30),
                ContactConversation.consent_to_followup.is_(True),
            ).limit(50)
        ).all()
        reviewed = 0
        for conversation in conversations:
            already_reviewed = db.scalar(select(ContactMessage.id).where(
                ContactMessage.conversation_id == conversation.id,
                ContactMessage.role == "system",
                ContactMessage.created_at >= now - __import__('datetime').timedelta(minutes=30),
            ).limit(1))
            if already_reviewed:
                continue
            history = db.scalars(select(ContactMessage).where(ContactMessage.conversation_id == conversation.id).order_by(ContactMessage.created_at)).all()
            transcript = "\n".join(f"{m.role}: {m.content[:1500]}" for m in history[-10:])
            prompt = ("Analisa a conversa e devolve um plano de seguimento curto, em português europeu. "
                      "Não envies mensagens, não inventes factos e indica se é necessária intervenção humana.")
            suggestion = bedrock_generate(prompt, transcript, max_tokens=500, temperature=0.2)
            db.add(ContactMessage(conversation_id=conversation.id, role="system", content=suggestion,
                                  delivery_status="draft" if config.mode == "approval" else "suggestion"))
            reviewed += 1
        db.add(AuditLog(action="contact_ai.cycle_completed", entity_type="contact_ai", entity_id="1",
                        details={"reviewed_conversations": reviewed, "mode": config.mode}))
        db.commit()
        return {"status": "completed", "reviewed": reviewed, "mode": config.mode}
    except AIUnavailable as exc:
        db.rollback()
        return {"status": "error", "reason": str(exc)}
    finally:
        db.close()


@celery.task(name="app.workers.contact_ai_tasks.run_scheduled_property_discovery")
def run_scheduled_property_discovery():
    """Run due administrator-configured web discovery and save a report for human review."""
    from app.services.ai import research_web
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        config = db.get(ContactAISettings, 1)
        if not config or not config.search_enabled:
            return {"status": "disabled"}
        if config.next_search_at and config.next_search_at > now:
            return {"status": "not_due"}
        query = (config.search_query or "").strip()
        if not query:
            return {"status": "invalid_query"}
        config.last_search_at = now
        config.next_search_at = now + timedelta(minutes=max(60, min(config.search_interval_minutes, 10080)))
        db.commit()
        result = research_web(query)
        db.add(AuditLog(action="property_discovery.automatic_completed", entity_type="property_search",
                        entity_id="scheduled", details={"query": query, "report": result.get("text", "")[:16000],
                        "sources": result.get("sources", []), "requires_human_review": True}))
        db.commit()
        return {"status": "completed", "source_count": len(result.get("sources", []))}
    except AIUnavailable as exc:
        db.rollback()
        return {"status": "error", "reason": str(exc)}
    except Exception as exc:
        db.rollback()
        return {"status": "error", "reason": type(exc).__name__}
    finally:
        db.close()
