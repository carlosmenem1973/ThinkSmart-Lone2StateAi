import secrets
import boto3
import string

from datetime import datetime, timedelta, timezone

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    Response,
)

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.core.auth import get_business_user
from app.models.entities import User
from app.core.config import settings
from app.agents.registry import AGENTS
from app.core.database import get_db

router = APIRouter()

@router.get(
    "/ai/status",
    summary="Get AI provider status",
    tags=["AI"],
)
def get_ai_status(
    user: User = Depends(get_business_user),
):
    """
    Return the configured AI providers and capabilities.

    Configuration status does not guarantee AWS runtime availability.
    """
    bedrock_enabled = bool(
        settings.bedrock_model_id and settings.aws_region
    )

    web_search_enabled = bool(
        settings.agentcore_web_search_id
    )

    return {
        "enabled": bedrock_enabled,
        "provider": "amazon-bedrock",
        "model": settings.bedrock_model_id or None,
        "region": settings.aws_region,
        "web_search": {
            "enabled": web_search_enabled,
            "provider": "amazon-bedrock-agentcore",
            "search_id": settings.agentcore_web_search_id or None,
            "max_results": settings.agentcore_web_search_max_results,
        },
    }


# ============================================================================
# AI AGENTS
# ============================================================================

@router.get(
    "/agents",
    summary="List available AI agents",
    tags=["AI"],
)
def list_agents(
    user: User = Depends(get_business_user),
):
    """
    Return all registered ThinkSmart AI agents.
    """
    agents = [
        {
            "id": agent_id,
            "name": agent.get("name", agent_id),
            "description": agent.get("description", ""),
            "source": agent.get("source", "internal"),
        }
        for agent_id, agent in AGENTS.items()
    ]

    return {
        "agents": agents,
        "total": len(agents),
    }


@router.post("/agents/{agent_id}/run")
def run_agent(
    agent_id: str,
    payload: dict | None = None,
    user: User = Depends(get_business_user),
    db: Session = Depends(get_db),
):
    require_write_access(user)

    if agent_id not in AGENTS:
        raise HTTPException(status_code=404, detail="Agent not found")

    payload = payload or {}
    query = str(payload.get("query") or "").strip()

    try:
        context = {
            "agent": AGENTS[agent_id],
            "user_role": user.role.value,
        }

        if agent_id in {"property-discovery", "owner-intelligence"}:
            search_query = query or (
                "Oportunidades imobili├írias p├║blicas ├á venda em Portugal"
            )
            context["query"] = search_query
            context["web_results"] = search_web(
                search_query[:200],
                max_results=settings.agentcore_web_search_max_results,
            )

        elif agent_id == "market-analyst":
            search_query = query or (
                "Mercado imobili├írio em Portugal: tend├¬ncias e pre├ºos"
            )
            context["web_results"] = search_web(search_query[:200], max_results=8)

            q = select(Lead).order_by(Lead.created_at.desc()).limit(60)
            if user.role not in {UserRole.SUPER_ADMIN, UserRole.ADMIN}:
                q = q.where(Lead.assigned_to == user.id)

            context["internal_leads"] = [
                {
                    "title": x.title,
                    "municipality": x.municipality,
                    "property_type": x.property_type,
                    "score": x.score,
                    "status": x.status.value,
                }
                for x in db.scalars(q).all()
            ]

        elif agent_id == "lead-qualifier":
            q = select(Lead).order_by(Lead.created_at.desc()).limit(100)
            if user.role not in {UserRole.SUPER_ADMIN, UserRole.ADMIN}:
                q = q.where(Lead.assigned_to == user.id)

            context["leads"] = [
                {
                    "id": x.id,
                    "title": x.title,
                    "municipality": x.municipality,
                    "property_type": x.property_type,
                    "score": x.score,
                    "score_reason": x.score_reason,
                    "status": x.status.value,
                    "source_name": x.source_name,
                }
                for x in db.scalars(q).all()
            ]

        elif agent_id == "email-intelligence":
            q = select(EmailInsight).order_by(
                EmailInsight.processed_at.desc()
            ).limit(50)

            if user.role not in {UserRole.SUPER_ADMIN, UserRole.ADMIN}:
                q = q.where(EmailInsight.mailbox == user.email)

            context["email_insights"] = [
                {
                    "subject": x.subject,
                    "sender": x.sender,
                    "received_at": x.received_at,
                    "summary": x.summary,
                    "extracted_data": x.extracted_data,
                }
                for x in db.scalars(q).all()
            ]

        elif agent_id == "follow-up-assistant":
            q = select(FollowUp).where(
                FollowUp.completed.is_(False)
            ).order_by(FollowUp.due_at).limit(100)

            if user.role not in {UserRole.SUPER_ADMIN, UserRole.ADMIN}:
                q = q.where(FollowUp.seller_id == user.id)

            context["followups"] = [
                {
                    "id": x.id,
                    "lead_id": x.lead_id,
                    "due_at": x.due_at,
                    "note": x.note,
                    "lead_title": x.lead.title if x.lead else None,
                }
                for x in db.scalars(q).all()
            ]

        if query:
            context["user_query"] = query[:1000]

        result = run_agent_prompt(agent_id, context)

    except (AIUnavailable, ValueError) as exc:
        raise HTTPException(
            status_code=502,
            detail="Agent execution failed. Check Bedrock and AgentCore permissions.",
        ) from exc

    audit(db, user, "agent.executed", "agent", agent_id, {"agent_id": agent_id})
    db.commit()

    return {
        "agent_id": agent_id,
        "text": result,
        "message": result,
        "result": {"text": result},
    }

