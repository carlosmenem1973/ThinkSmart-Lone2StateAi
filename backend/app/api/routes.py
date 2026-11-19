import asyncio
import secrets
import boto3
import string
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import func, select, or_
from sqlalchemy.orm import Session

from app.core.auth import (
    clear_refresh_cookie, create_access_token, get_current_user, get_business_user,
    hash_password, hash_refresh_token, require_admin_user, require_lead_access,
    set_refresh_cookie, verify_password, verify_same_origin,
)
from app.core.config import settings
from app.core.database import get_db
from app.models.entities import (
    AuditLog, DraftStatus, FollowUp, Lead, LeadStatus, OutreachDraft,
    RefreshSession, User, UserRole, BrandSettings,
)
from app.schemas.auth import ChangePasswordRequest, CreateUserRequest, LoginRequest, UserOut
from app.schemas.leads import LeadCreate, LeadOut, LeadUpdate, FollowUpCreate
from app.schemas.branding import BrandingUpdate
from app.services.ai import research_web, draft_outreach, client as ai_client
from app.agents.registry import AGENTS, AGENT_RUNNERS
from agents import Runner

router = APIRouter()


def validate_password_strength(value: str) -> None:
    if len(value) < 12 or not any(c.islower() for c in value) or not any(c.isupper() for c in value) or not any(c.isdigit() for c in value):
        raise HTTPException(status_code=400, detail="Password must be at least 12 characters and include upper-case, lower-case and numeric characters")


def generate_temporary_password() -> str:
    groups = [string.ascii_lowercase, string.ascii_uppercase, string.digits]
    chars = [secrets.choice(group) for group in groups]
    alphabet = string.ascii_letters + string.digits
    chars.extend(secrets.choice(alphabet) for _ in range(21))
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)


def user_public(user: User) -> dict:
    return {
        "id": user.id, "email": user.email, "full_name": user.full_name,
        "role": user.role.value, "territory": user.territory,
        "active": user.active, "must_change_password": user.must_change_password,
    }


def create_refresh_session(db: Session, user: User, request: Request) -> str:
    raw = secrets.token_urlsafe(48)
    session = RefreshSession(
        user_id=user.id,
        token_hash=hash_refresh_token(raw),
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_days),
        user_agent=request.headers.get("user-agent", "")[:500] or None,
        ip_address=request.client.host if request.client else None,
    )
    db.add(session)
    return raw


def audit(db: Session, actor: User | None, action: str, entity_type: str, entity_id: str, details: dict | None = None):
    db.add(AuditLog(actor_id=actor.id if actor else None, action=action, entity_type=entity_type, entity_id=entity_id, details=details or {}))






def require_write_access(user: User) -> None:
    if user.role == UserRole.VIEWER:
        raise HTTPException(status_code=403, detail="Viewer accounts have read-only access")

def branding_public(settings_row: BrandSettings | None) -> dict:
    if settings_row is None:
        return {
            "product_name": "ThinkSmart AI", "customer_name": "Loft2 Real Estate",
            "tagline": "Real Estate Intelligence", "logo_url": None,
            "primary_color": "#2563EB", "accent_color": "#16866C",
        }
    return {
        "product_name": settings_row.product_name, "customer_name": settings_row.customer_name,
        "tagline": settings_row.tagline, "logo_url": settings_row.logo_url,
        "primary_color": settings_row.primary_color, "accent_color": settings_row.accent_color,
    }


@router.get("/settings/branding")
def get_branding(db: Session = Depends(get_db)):
    # Public endpoint exposes display-only metadata for the login screen.
    # Avoid writes from unauthenticated GET requests.
    return branding_public(db.get(BrandSettings, 1))


@router.put("/settings/branding")
def update_branding(payload: BrandingUpdate, user: User = Depends(require_admin_user), db: Session = Depends(get_db)):
    row = db.get(BrandSettings, 1)
    if row is None:
        row = BrandSettings(id=1)
        db.add(row)
    for key, value in payload.model_dump().items():
        setattr(row, key, value)
    row.updated_by = user.id
    audit(db, user, "settings.branding_updated", "brand_settings", "1", payload.model_dump())
    db.commit()
    db.refresh(row)
    return branding_public(row)


@router.get("/health")
def health():
    return {"status": "ok", "service": settings.app_name}


@router.post("/auth/login", include_in_schema=False)
def login_deprecated():
    raise HTTPException(status_code=410, detail="Local password login is disabled. Authenticate directly with Amazon Cognito.")


@router.post("/auth/refresh", include_in_schema=False)
def refresh_deprecated():
    raise HTTPException(status_code=410, detail="Local refresh cookies are disabled. Use Cognito fetchAuthSession().")


@router.post("/auth/logout", include_in_schema=False)
def logout_deprecated():
    raise HTTPException(status_code=410, detail="Use Amazon Cognito signOut().")


@router.get("/auth/me")
def me(principal = Depends(get_current_user)):
    # This endpoint is deliberately independent of PostgreSQL.
    return {
        "id": principal.sub,
        "sub": principal.sub,
        "email": principal.email,
        "full_name": principal.name,
        "role": principal.role.value,
        "groups": sorted(principal.groups),
        "active": True,
        "must_change_password": False,
        "territory": None,
    }


@router.post("/auth/change-password", include_in_schema=False)
def change_password_deprecated():
    raise HTTPException(status_code=410, detail="Change passwords through Amazon Cognito.")


@router.get("/auth/users", response_model=list[UserOut])
def list_users(_admin: User = Depends(require_admin_user), db: Session = Depends(get_db)):
    return db.scalars(select(User).order_by(User.role, User.full_name)).all()


@router.post("/auth/users", status_code=201)
def create_user(payload: CreateUserRequest, admin: User = Depends(require_admin_user), db: Session = Depends(get_db)):
    email = str(payload.email).lower().strip()
    if db.scalar(select(User).where(func.lower(User.email) == email)):
        raise HTTPException(status_code=409, detail="An application account with this email already exists")
    if not settings.cognito_user_pool_id:
        raise HTTPException(status_code=503, detail="Cognito User Pool is not configured")
    try:
        client = boto3.client("cognito-idp", region_name=settings.aws_region)
        result = client.admin_create_user(
            UserPoolId=settings.cognito_user_pool_id,
            Username=email,
            UserAttributes=[
                {"Name": "email", "Value": email},
                {"Name": "name", "Value": payload.full_name},
            ],
            DesiredDeliveryMediums=["EMAIL"],
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Cognito user provisioning failed: {type(exc).__name__}")
    attributes = {item["Name"]: item["Value"] for item in result.get("User", {}).get("Attributes", [])}
    cognito_sub = attributes.get("sub")
    if not cognito_sub:
        raise HTTPException(status_code=502, detail="Cognito created the user but did not return a subject")
    cognito_group = {
        UserRole.SUPER_ADMIN: "SUPER_ADMIN",
        UserRole.ADMIN: "ADMIN",
        UserRole.MANAGER: "MANAGER",
        UserRole.SELLER: "SELLER",
        UserRole.VIEWER: "VIEWER",
    }[payload.role]
    try:
        client.admin_add_user_to_group(
            UserPoolId=settings.cognito_user_pool_id,
            Username=email,
            GroupName=cognito_group,
        )
    except Exception as exc:
        # Avoid persisting an app profile when Cognito group assignment failed.
        try:
            client.admin_delete_user(UserPoolId=settings.cognito_user_pool_id, Username=email)
        except Exception:
            pass
        raise HTTPException(status_code=502, detail=f"Cognito group assignment failed: {type(exc).__name__}")

    user = User(
        email=email, full_name=payload.full_name, role=payload.role,
        territory=payload.territory, active=True, cognito_sub=cognito_sub,
        password_hash=None, must_change_password=False,
    )
    db.add(user)
    db.flush()
    audit(db, admin, "user.created", "user", str(user.id), {"email": email, "role": user.role.value, "identity_provider": "cognito"})
    db.commit()
    return {"user": user_public(user), "message": "Cognito invitation sent to the user's email address."}


@router.post("/auth/users/{user_id}/reset-password")
def reset_user_password(user_id: int, admin: User = Depends(require_admin_user), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user or not user.cognito_sub:
        raise HTTPException(status_code=404, detail="Cognito-linked user not found")
    try:
        boto3.client("cognito-idp", region_name=settings.aws_region).admin_reset_user_password(
            UserPoolId=settings.cognito_user_pool_id, Username=user.email
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Cognito password reset failed: {type(exc).__name__}")
    audit(db, admin, "user.password_reset", "user", str(user.id), {"identity_provider": "cognito"})
    db.commit()
    return {"user_id": user.id, "message": "Cognito password reset initiated. The user will receive the Cognito reset email."}


@router.patch("/auth/users/{user_id}/active")
def set_user_active(user_id: int, active: bool, admin: User = Depends(require_admin_user), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == admin.id and not active:
        raise HTTPException(status_code=400, detail="You cannot deactivate your own administrator account")
    if user.role in {UserRole.SUPER_ADMIN, UserRole.ADMIN} and not active:
        active_admins = db.scalar(select(func.count()).select_from(User).where(User.role.in_([UserRole.SUPER_ADMIN, UserRole.ADMIN]), User.active.is_(True))) or 0
        if active_admins <= 1:
            raise HTTPException(status_code=400, detail="At least one active administrator must remain")
    if user.cognito_sub:
        try:
            cognito = boto3.client("cognito-idp", region_name=settings.aws_region)
            operation = cognito.admin_enable_user if active else cognito.admin_disable_user
            operation(UserPoolId=settings.cognito_user_pool_id, Username=user.email)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Cognito account update failed: {type(exc).__name__}")
    user.active = active
    user.token_version = (user.token_version or 0) + 1
    if not active:
        for session in db.scalars(select(RefreshSession).where(RefreshSession.user_id == user.id, RefreshSession.revoked_at.is_(None))).all():
            session.revoked_at = datetime.now(timezone.utc)
    audit(db, admin, "user.active_changed", "user", str(user.id), {"active": active})
    db.commit()
    return user_public(user)


@router.get("/dashboard")
def dashboard(user: User = Depends(get_business_user), db: Session = Depends(get_db)):
    lead_filter = [] if user.role in {UserRole.SUPER_ADMIN, UserRole.ADMIN} else [Lead.assigned_to == user.id]
    followup_filter = [] if user.role in {UserRole.SUPER_ADMIN, UserRole.ADMIN} else [FollowUp.seller_id == user.id]
    draft_filter = [] if user.role in {UserRole.SUPER_ADMIN, UserRole.ADMIN} else [OutreachDraft.created_by == user.id]
    counts = {s.value: db.scalar(select(func.count()).select_from(Lead).where(Lead.status == s, *lead_filter)) or 0 for s in LeadStatus}
    return {
        "total_leads": sum(counts.values()), "by_status": counts,
        "pending_followups": db.scalar(select(func.count()).select_from(FollowUp).where(FollowUp.completed.is_(False), *followup_filter)) or 0,
        "pending_drafts": db.scalar(select(func.count()).select_from(OutreachDraft).where(OutreachDraft.status == DraftStatus.PENDING, *draft_filter)) or 0,
        "current_user": user_public(user),
    }


@router.get("/sellers")
def list_sellers(_admin: User = Depends(require_admin_user), db: Session = Depends(get_db)):
    sellers = db.scalars(select(User).where(User.role == UserRole.SELLER, User.active.is_(True)).order_by(User.full_name)).all()
    return [{"id": u.id, "email": u.email, "full_name": u.full_name, "territory": u.territory} for u in sellers]


@router.get("/leads", response_model=list[LeadOut])
def list_leads(status: LeadStatus | None = None, user: User = Depends(get_business_user), db: Session = Depends(get_db)):
    q = select(Lead).order_by(Lead.created_at.desc()).limit(250)
    if user.role not in {UserRole.SUPER_ADMIN, UserRole.ADMIN}:
        q = q.where(Lead.assigned_to == user.id)
    if status:
        q = q.where(Lead.status == status)
    return db.scalars(q).all()


@router.post("/leads", response_model=LeadOut)
def create_lead(payload: LeadCreate, user: User = Depends(get_business_user), db: Session = Depends(get_db)):
    require_write_access(user)
    if payload.source_url and db.scalar(select(Lead).where(Lead.source_url == payload.source_url)):
        raise HTTPException(status_code=409, detail="Source URL already exists")
    values = payload.model_dump()
    if user.role not in {UserRole.SUPER_ADMIN, UserRole.ADMIN}:
        values["assigned_to"] = user.id
        values["outreach_allowed"] = False
        values["lawful_basis"] = None
    elif values.get("assigned_to"):
        assigned_user = db.get(User, values["assigned_to"])
        if not assigned_user or not assigned_user.active or assigned_user.role != UserRole.SELLER:
            raise HTTPException(status_code=400, detail="Assigned user must be an active seller")
    lead = Lead(**values)
    db.add(lead)
    db.flush()
    audit(db, user, "lead.created", "lead", str(lead.id))
    db.commit()
    db.refresh(lead)
    return lead


@router.patch("/leads/{lead_id}", response_model=LeadOut)
def update_lead(lead_id: int, payload: LeadUpdate, user: User = Depends(get_business_user), db: Session = Depends(get_db)):
    require_write_access(user)
    lead = db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    require_lead_access(user, lead)
    changes = payload.model_dump(exclude_unset=True)
    if user.role not in {UserRole.SUPER_ADMIN, UserRole.ADMIN} and ({"assigned_to", "outreach_allowed", "lawful_basis"} & changes.keys()):
        raise HTTPException(status_code=403, detail="Only administrators can reassign leads or change outreach authorisation")
    for key, value in changes.items():
        setattr(lead, key, value)
    audit(db, user, "lead.updated", "lead", str(lead_id), {k: str(v) for k, v in changes.items()})
    db.commit()
    db.refresh(lead)
    return lead


@router.post("/research")
def run_research(
    query: str,
    source: str = "web",
    user: User = Depends(get_business_user),
    db: Session = Depends(get_db),
):
    """Run web research or search the signed-in user's permitted internal lead records."""
    require_write_access(user)
    query = query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Introduza uma pesquisa.")
    if len(query) > 1000:
        raise HTTPException(status_code=413, detail="A pesquisa excede o limite de 1.000 caracteres.")

    if source == "internal":
        pattern = f"%{query}%"
        statement = select(Lead).where(or_(
            Lead.title.ilike(pattern),
            Lead.address.ilike(pattern),
            Lead.municipality.ilike(pattern),
            Lead.district.ilike(pattern),
            Lead.source_name.ilike(pattern),
            Lead.evidence.ilike(pattern),
        )).order_by(Lead.created_at.desc()).limit(100)
        if user.role not in {UserRole.SUPER_ADMIN, UserRole.ADMIN}:
            statement = statement.where(Lead.assigned_to == user.id)
        matches = db.scalars(statement).all()
        items = [{
            "id": lead.id,
            "title": lead.title,
            "address": lead.address,
            "municipality": lead.municipality,
            "district": lead.district,
            "source_name": lead.source_name,
            "source_url": lead.source_url,
            "score": lead.score,
            "status": lead.status.value if lead.status else None,
        } for lead in matches]
        result = {
            "source": "internal",
            "count": len(items),
            "items": items,
            "text": (
                f"Foram encontradas {len(items)} oportunidades nos registos a que tem acesso."
                if items else "Não foram encontradas oportunidades correspondentes nos registos a que tem acesso."
            ),
        }
    elif source == "web":
        try:
            result = research_web(query)
        except Exception as exc:
            # Avoid exposing provider payloads, credentials, or internal request details.
            raise HTTPException(
                status_code=502,
                detail=f"Falha no fornecedor de pesquisa ({type(exc).__name__}). Verifique a chave e o modelo configurados no backend.",
            ) from exc
    else:
        raise HTTPException(status_code=422, detail="A origem deve ser 'web' ou 'internal'.")

    audit(db, user, "research.executed", "research", result.get("response_id", "internal"), {
        "query": query[:500], "source": source, "result_count": result.get("count"),
    })
    db.commit()
    return result


@router.get("/agents")
def list_agents(_user: User = Depends(get_business_user)):
    """List the six supported agents for the signed-in workspace."""
    return {"items": [
        {
            "id": agent_id,
            "name": spec["name"],
            "description": spec["description"],
            "purpose": spec["purpose"],
        }
        for agent_id, spec in AGENTS.items()
    ]}


@router.post("/agents/{agent_id}/run")
async def execute_agent(
    agent_id: str,
    request: Request,
    user: User = Depends(get_business_user),
    db: Session = Depends(get_db),
):
    """Execute a registered agent and return output explicitly marked for human review."""
    require_write_access(user)
    if agent_id not in AGENT_RUNNERS:
        raise HTTPException(status_code=404, detail="Agente não encontrado.")
    if ai_client is None:
        raise HTTPException(status_code=503, detail="O serviço de IA não está configurado. Verifique OPENAI_API_KEY.")

    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}
    supplied = str(body.get("input") or body.get("query") or "").strip()
    if len(supplied) > 12000:
        raise HTTPException(status_code=413, detail="O pedido excede o limite de 12.000 caracteres.")

    if agent_id == "email-intelligence" and not supplied:
        raise HTTPException(status_code=400, detail="Forneça o texto do email autorizado para análise.")
    if agent_id in {"owner-intelligence", "lead-qualifier", "follow-up-assistant"} and not supplied:
        raise HTTPException(status_code=400, detail="Forneça os dados ou contexto que o agente deve analisar.")

    # These two agents use the existing Responses API web-search service. The
    # other agents use the Agents SDK and only the content supplied by the user.
    try:
        if agent_id in {"property-discovery", "market-analyst"}:
            task = AGENTS[agent_id]["instructions"] + "\nPedido: " + (
                supplied or "Identifica oportunidades e tendências recentes no mercado imobiliário português."
            )
            output = (await asyncio.to_thread(research_web, task)).get("text", "")
        else:
            result = await Runner.run(AGENT_RUNNERS[agent_id], supplied)
            output = getattr(result, "final_output", None) or str(result)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Falha na execução do agente ({type(exc).__name__}). Verifique o modelo e a configuração de IA.",
        ) from exc

    audit(db, user, "agent.executed", "agent", agent_id, {"input_length": len(supplied)})
    db.commit()
    return {
        "agent_id": agent_id,
        "status": "completed",
        "text": str(output),
        "requires_human_review": True,
    }


@router.post("/leads/{lead_id}/draft")
def create_draft(lead_id: int, user: User = Depends(get_business_user), db: Session = Depends(get_db)):
    require_write_access(user)
    lead = db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    require_lead_access(user, lead)
    if not lead.owner_email:
        raise HTTPException(status_code=400, detail="No verified recipient email on lead")
    if not lead.outreach_allowed or not lead.lawful_basis:
        raise HTTPException(status_code=403, detail="A documented lawful basis and channel permission are required before preparing outreach")
    result = draft_outreach({"title": lead.title, "address": lead.address, "owner_name": lead.owner_name, "evidence": lead.evidence, "lawful_basis": lead.lawful_basis, "outreach_allowed": lead.outreach_allowed})
    draft = OutreachDraft(lead_id=lead.id, created_by=user.id, recipient=lead.owner_email, subject=result.get("subject", "Pedido de informação"), body=result.get("body", result.get("message", "")))
    db.add(draft)
    db.flush()
    audit(db, user, "outreach_draft.created", "draft", str(draft.id), {"lead_id": lead.id})
    db.commit()
    db.refresh(draft)
    return {"id": draft.id, "status": draft.status, "subject": draft.subject, "body": draft.body, "ai_warning": result.get("warning")}


@router.post("/drafts/{draft_id}/approve")
def approve_draft(draft_id: int, user: User = Depends(get_business_user), db: Session = Depends(get_db)):
    require_write_access(user)
    draft = db.get(OutreachDraft, draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    lead = db.get(Lead, draft.lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    require_lead_access(user, lead)
    if user.role not in {UserRole.SUPER_ADMIN, UserRole.ADMIN} and draft.created_by != user.id:
        raise HTTPException(status_code=404, detail="Draft not found")
    if not lead.outreach_allowed or not lead.lawful_basis:
        raise HTTPException(status_code=403, detail="Cannot approve: documented outreach permission/lawful basis is missing")
    draft.status = DraftStatus.APPROVED
    draft.approved_at = datetime.now(timezone.utc)
    audit(db, user, "outreach_draft.approved", "draft", str(draft.id))
    db.commit()
    return {"status": "approved", "message": "Draft approved. Sending is not enabled; copy it to your authorised email client."}


@router.post("/leads/{lead_id}/followups")
def create_followup(lead_id: int, payload: FollowUpCreate, user: User = Depends(get_business_user), db: Session = Depends(get_db)):
    require_write_access(user)
    lead = db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    require_lead_access(user, lead)
    seller_id = user.id if user.role not in {UserRole.SUPER_ADMIN, UserRole.ADMIN} else payload.seller_id
    seller = db.get(User, seller_id)
    if not seller or not seller.active or seller.role != UserRole.SELLER:
        raise HTTPException(status_code=400, detail="Follow-up must be assigned to an active seller")
    followup = FollowUp(lead_id=lead_id, seller_id=seller_id, due_at=payload.due_at, note=payload.note)
    db.add(followup)
    db.flush()
    audit(db, user, "followup.created", "followup", str(followup.id))
    db.commit()
    return {"id": followup.id, "due_at": followup.due_at, "completed": followup.completed}


@router.get("/followups")
def list_followups(user: User = Depends(get_business_user), db: Session = Depends(get_db)):
    q = select(FollowUp).where(FollowUp.completed.is_(False)).order_by(FollowUp.due_at)
    if user.role not in {UserRole.SUPER_ADMIN, UserRole.ADMIN}:
        q = q.where(FollowUp.seller_id == user.id)
    rows = db.scalars(q).all()
    return [{"id": x.id, "lead_id": x.lead_id, "seller_id": x.seller_id, "due_at": x.due_at, "note": x.note} for x in rows]


@router.get("/integrations/microsoft/status")
def microsoft_status(_user: User = Depends(get_business_user)):
    return {"configured": bool(settings.microsoft_client_id and settings.microsoft_client_secret), "mailbox_sync_enabled": False, "message": "Per-seller Entra OAuth state binding and encrypted token-cache persistence must be configured before mailbox synchronisation."}
