"""Build privacy-minimised CRM matching context for specialist agents."""
from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.contact import Contact
from app.models.entities import Lead, LeadStatus, User, UserRole
from app.services.property_matching import property_payload, score_client_property

MANAGEMENT_ROLES = {UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.MANAGER}
INACTIVE_LEAD_STATUSES = {LeadStatus.LOST, LeadStatus.SUPPRESSED}


def _phone(value: str | None) -> str:
    return "".join(char for char in (value or "") if char.isdigit())


def _lead_scope(user: User):
    statement = select(Lead).where(Lead.status.notin_(INACTIVE_LEAD_STATUSES))
    if user.role not in MANAGEMENT_ROLES:
        statement = statement.where(Lead.assigned_to == user.id)
    return statement


def _contact_scope(user: User):
    statement = select(Contact).where(Contact.active.is_(True))
    if user.role not in MANAGEMENT_ROLES:
        statement = statement.where(or_(Contact.assigned_to == user.id, Contact.created_by == user.id))
    return statement


def build_agent_matching_context(
    db: Session,
    user: User,
    *,
    contact_id: int | None = None,
    lead_id: int | None = None,
) -> str:
    """Return a bounded CRM matching summary. Never returns phone numbers or email addresses."""
    if bool(contact_id) == bool(lead_id):
        raise ValueError("Indique exatamente um contact_id ou lead_id.")

    if contact_id is not None:
        contact = db.scalar(_contact_scope(user).where(Contact.id == contact_id))
        if contact is None:
            raise LookupError("Contacto não encontrado ou sem permissões.")
        if contact.contact_type == "client":
            leads = db.scalars(_lead_scope(user).order_by(Lead.updated_at.desc()).limit(500)).all()
            ranked = []
            for lead in leads:
                result = score_client_property(contact, lead)
                if result["score"] >= 35:
                    ranked.append(property_payload(lead, result))
            ranked.sort(key=lambda item: (item["score"], item.get("lead_id", 0)), reverse=True)
            items = [{
                "lead_id": item["lead_id"], "title": item["title"],
                "municipality": item["municipality"], "district": item["district"],
                "property_type": item["property_type"], "price": item["price"],
                "area": item["area"], "bedrooms": item["bedrooms"],
                "score": item["score"], "explanation": item["explanation"],
            } for item in ranked[:10]]
            heading = f"Cliente CRM {contact.full_name}: imóveis compatíveis"
            note = "Correspondências determinísticas calculadas com dados atuais; campos ausentes não foram inferidos."
        elif contact.contact_type == "owner":
            clauses = []
            if contact.email:
                clauses.append(func.lower(Lead.owner_email) == contact.email.strip().lower())
            phone = _phone(contact.phone)
            if phone:
                clauses.append(func.regexp_replace(Lead.owner_phone, r"\\D", "", "g") == phone)
            leads = db.scalars(_lead_scope(user).where(or_(*clauses)).limit(100)).all() if clauses else []
            items = [{
                "lead_id": lead.id, "title": lead.title,
                "municipality": lead.municipality, "district": lead.district,
                "source_url": lead.source_url,
                "link_basis": "email_or_phone_exact_match",
                "owner_identity_verified": False,
            } for lead in leads]
            heading = f"Contacto CRM do tipo proprietário {contact.full_name}: anúncios associados"
            note = "A associação por email/telefone identifica registos coincidentes; não comprova titularidade legal."
        else:
            raise ValueError("Tipo de contacto não suportado para matching.")
        return f"{heading}\n{note}\nResultados: {items}"

    lead = db.scalar(_lead_scope(user).where(Lead.id == lead_id))
    if lead is None:
        raise LookupError("Imóvel/oportunidade não encontrado ou sem permissões.")
    clients = db.scalars(_contact_scope(user).where(Contact.contact_type == "client").limit(500)).all()
    ranked = []
    for contact in clients:
        result = score_client_property(contact, lead)
        if result["score"] >= 35:
            ranked.append({
                "contact_id": contact.id, "name": contact.full_name,
                "municipality": contact.municipality,
                "budget_min": contact.budget_min, "budget_max": contact.budget_max,
                "score": result["score"], "explanation": result["explanation"],
            })
    ranked.sort(key=lambda item: (item["score"], item["contact_id"]), reverse=True)
    property_info = {
        "lead_id": lead.id, "title": lead.title,
        "municipality": lead.municipality, "district": lead.district,
        "property_type": lead.property_type, "address": lead.address,
    }
    return (
        f"Imóvel CRM: {property_info}\n"
        "Potenciais clientes (dados de contacto omitidos; matching determinístico): "
        f"{ranked[:10]}\n"
        "Não contactar automaticamente. A identidade, interesse atual, consentimento e adequação "
        "do canal têm de ser confirmados por uma pessoa."
    )
