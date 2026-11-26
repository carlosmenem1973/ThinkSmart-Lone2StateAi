"""CRM matching endpoints for client/property and owner/property relationships."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.auth import get_business_user
from app.core.database import get_db
from app.models.contact import Contact
from app.models.entities import Lead, LeadStatus, User, UserRole
from app.services.property_matching import property_payload, score_client_property

router = APIRouter(prefix="/matching", tags=["Property matching"])
MANAGEMENT_ROLES = {UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.MANAGER}
INACTIVE_LEAD_STATUSES = {LeadStatus.LOST, LeadStatus.SUPPRESSED}


def _contact_for_user(db: Session, contact_id: int, user: User) -> Contact:
    statement = select(Contact).where(Contact.id == contact_id)
    if user.role not in MANAGEMENT_ROLES:
        statement = statement.where(or_(Contact.assigned_to == user.id, Contact.created_by == user.id))
    contact = db.scalar(statement)
    if contact is None or not contact.active:
        raise HTTPException(status_code=404, detail="Contacto não encontrado.")
    return contact


def _lead_for_user(db: Session, lead_id: int, user: User) -> Lead:
    statement = select(Lead).where(Lead.id == lead_id)
    if user.role not in MANAGEMENT_ROLES:
        statement = statement.where(Lead.assigned_to == user.id)
    lead = db.scalar(statement)
    if lead is None:
        raise HTTPException(status_code=404, detail="Oportunidade imobiliária não encontrada.")
    return lead


def _lead_query(user: User):
    statement = select(Lead).where(Lead.status.notin_(INACTIVE_LEAD_STATUSES))
    if user.role not in MANAGEMENT_ROLES:
        statement = statement.where(Lead.assigned_to == user.id)
    return statement


def _contact_query(user: User):
    statement = select(Contact).where(Contact.active.is_(True))
    if user.role not in MANAGEMENT_ROLES:
        statement = statement.where(or_(Contact.assigned_to == user.id, Contact.created_by == user.id))
    return statement


def _normal_phone(value: str | None) -> str:
    return "".join(ch for ch in (value or "") if ch.isdigit())


@router.get("/contacts/{contact_id}/properties")
def match_properties_for_contact(
    contact_id: int,
    min_score: int = Query(default=35, ge=0, le=100),
    limit: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_business_user),
    db: Session = Depends(get_db),
):
    """For clients, rank available property leads. For owners, find leads explicitly linked by email/phone."""
    contact = _contact_for_user(db, contact_id, user)
    if contact.contact_type == "owner":
        clauses = []
        if contact.email:
            clauses.append(Lead.owner_email.ilike(contact.email.strip()))
        phone = _normal_phone(contact.phone)
        if phone:
            # Exact comparison after removing common punctuation is done in Python below.
            clauses.append(Lead.owner_phone.is_not(None))
        if not clauses:
            return {"contact_id": contact.id, "contact_type": "owner", "matches": [], "note": "O proprietário não tem email ou telefone para associação determinística."}
        candidates = db.scalars(_lead_query(user).where(or_(*clauses)).limit(500)).all()
        matches = []
        for lead in candidates:
            email_match = bool(contact.email and lead.owner_email and contact.email.strip().lower() == lead.owner_email.strip().lower())
            phone_match = bool(phone and _normal_phone(lead.owner_phone) == phone)
            if email_match or phone_match:
                matches.append({
                    "lead_id": lead.id, "title": lead.title, "address": lead.address,
                    "municipality": lead.municipality, "district": lead.district,
                    "source_url": lead.source_url,
                    "owner_link": "email" if email_match else "phone",
                    "owner_identity_verified": False,
                })
        return {"contact_id": contact.id, "contact_type": "owner", "matches": matches[:limit],
                "note": "A associação identifica um registo CRM, não comprova juridicamente a propriedade."}

    if contact.contact_type != "client":
        raise HTTPException(status_code=422, detail="Tipo de contacto não suportado.")
    leads = db.scalars(_lead_query(user).order_by(Lead.updated_at.desc()).limit(500)).all()
    matches = []
    for lead in leads:
        result = score_client_property(contact, lead)
        if result["score"] >= min_score:
            matches.append(property_payload(lead, result))
    matches.sort(key=lambda item: (item["score"], item.get("lead_id", 0)), reverse=True)
    return {"contact_id": contact.id, "contact_type": "client", "matches": matches[:limit],
            "candidate_count": len(leads), "matching_mode": "deterministic_on_demand"}


@router.get("/leads/{lead_id}/contacts")
def match_contacts_for_property(
    lead_id: int,
    contact_type: str = Query(default="client", pattern="^(client|owner)$"),
    min_score: int = Query(default=35, ge=0, le=100),
    limit: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_business_user),
    db: Session = Depends(get_db),
):
    """Find buyer/renter clients for a property, or link its owner contact by exact email/phone."""
    lead = _lead_for_user(db, lead_id, user)
    if contact_type == "owner":
        clauses = []
        if lead.owner_email:
            clauses.append(Contact.email.ilike(lead.owner_email.strip()))
        if lead.owner_phone:
            clauses.append(Contact.phone.is_not(None))
        candidates = db.scalars(_contact_query(user).where(Contact.contact_type == "owner").where(or_(*clauses)).limit(500)).all() if clauses else []
        matches = []
        for contact in candidates:
            email_match = bool(lead.owner_email and contact.email and lead.owner_email.strip().lower() == contact.email.strip().lower())
            phone_match = bool(lead.owner_phone and _normal_phone(contact.phone) == _normal_phone(lead.owner_phone))
            if email_match or phone_match:
                matches.append({"contact_id": contact.id, "full_name": contact.full_name,
                    "email": contact.email, "phone": contact.phone,
                    "match_basis": "email" if email_match else "phone",
                    "owner_identity_verified": False})
        return {"lead_id": lead.id, "contact_type": "owner", "matches": matches[:limit]}

    clients = db.scalars(_contact_query(user).where(Contact.contact_type == "client").limit(500)).all()
    matches = []
    for contact in clients:
        result = score_client_property(contact, lead)
        if result["score"] >= min_score:
            matches.append({"contact_id": contact.id, "full_name": contact.full_name,
                "municipality": contact.municipality, "budget_min": contact.budget_min,
                "budget_max": contact.budget_max, **result})
    matches.sort(key=lambda item: (item["score"], item["contact_id"]), reverse=True)
    return {"lead_id": lead.id, "contact_type": "client", "matches": matches[:limit],
            "candidate_count": len(clients), "matching_mode": "deterministic_on_demand"}
