import csv
import io
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr, Field, ConfigDict
from sqlalchemy import or_, select
from sqlalchemy.orm import Session
from app.core.auth import get_business_user
from app.core.database import get_db
from app.models.entities import AuditLog, User, UserRole
from app.models.contact import Contact

router = APIRouter(prefix="/contacts", tags=["Proprietários e Clientes"])

class ContactInput(BaseModel):
    contact_type: str = Field(pattern="^(owner|client)$")
    full_name: str = Field(min_length=2, max_length=160)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=80)
    municipality: str | None = Field(default=None, max_length=120)
    district: str | None = Field(default=None, max_length=120)
    property_preferences: str | None = Field(default=None, max_length=2000)
    budget_min: int | None = Field(default=None, ge=0)
    budget_max: int | None = Field(default=None, ge=0)
    source: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=5000)
    lawful_basis: str | None = Field(default=None, max_length=500)
    contact_permission: bool = False
    do_not_contact: bool = False
    active: bool = True

class ContactOut(ContactInput):
    model_config = ConfigDict(from_attributes=True)
    id: int
    assigned_to: int | None
    created_at: object
    updated_at: object

def _scope(query, user: User):
    if user.role not in {UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.MANAGER}:
        query = query.where(Contact.assigned_to == user.id)
    return query

def _audit(db, user, action, entity_id, details=None):
    db.add(AuditLog(actor_id=user.id, action=action, entity_type="contact", entity_id=str(entity_id), details=details or {}))

@router.get("", response_model=list[ContactOut])
def list_contacts(contact_type: str | None = Query(default=None, pattern="^(owner|client)$"), q: str | None = Query(default=None, max_length=160), active: bool | None = None, db: Session = Depends(get_db), user: User = Depends(get_business_user)):
    statement = _scope(select(Contact).order_by(Contact.updated_at.desc()).limit(500), user)
    if contact_type: statement = statement.where(Contact.contact_type == contact_type)
    if active is not None: statement = statement.where(Contact.active.is_(active))
    if q:
        pattern = f"%{q.strip()}%"
        statement = statement.where(or_(Contact.full_name.ilike(pattern), Contact.email.ilike(pattern), Contact.phone.ilike(pattern), Contact.municipality.ilike(pattern)))
    return db.scalars(statement).all()

@router.post("", response_model=ContactOut, status_code=201)
def create_contact(payload: ContactInput, db: Session = Depends(get_db), user: User = Depends(get_business_user)):
    if user.role == UserRole.VIEWER: raise HTTPException(403, "A conta tem acesso apenas de consulta.")
    if payload.budget_min is not None and payload.budget_max is not None and payload.budget_min > payload.budget_max: raise HTTPException(422, "O orçamento mínimo não pode exceder o máximo.")
    contact = Contact(**payload.model_dump(), assigned_to=user.id if user.role not in {UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.MANAGER} else None, created_by=user.id)
    db.add(contact); db.flush(); _audit(db, user, "contact.created", contact.id, {"contact_type": contact.contact_type}); db.commit(); db.refresh(contact)
    return contact

@router.patch("/{contact_id}", response_model=ContactOut)
def update_contact(contact_id: int, payload: ContactInput, db: Session = Depends(get_db), user: User = Depends(get_business_user)):
    if user.role == UserRole.VIEWER: raise HTTPException(403, "A conta tem acesso apenas de consulta.")
    contact = db.scalar(_scope(select(Contact).where(Contact.id == contact_id), user))
    if not contact: raise HTTPException(404, "Contacto não encontrado.")
    values = payload.model_dump()
    if values.get("budget_min") is not None and values.get("budget_max") is not None and values["budget_min"] > values["budget_max"]: raise HTTPException(422, "O orçamento mínimo não pode exceder o máximo.")
    for key, value in values.items(): setattr(contact, key, value)
    _audit(db, user, "contact.updated", contact.id, {"fields": sorted(values.keys())}); db.commit(); db.refresh(contact)
    return contact

@router.delete("/{contact_id}", status_code=204)
def archive_contact(contact_id: int, db: Session = Depends(get_db), user: User = Depends(get_business_user)):
    if user.role == UserRole.VIEWER: raise HTTPException(403, "A conta tem acesso apenas de consulta.")
    contact = db.scalar(_scope(select(Contact).where(Contact.id == contact_id), user))
    if not contact: raise HTTPException(404, "Contacto não encontrado.")
    contact.active = False; _audit(db, user, "contact.archived", contact.id); db.commit()
    return None

@router.post("/import")
def import_contacts(payload: dict, db: Session = Depends(get_db), user: User = Depends(get_business_user)):
    if user.role == UserRole.VIEWER: raise HTTPException(403, "A conta tem acesso apenas de consulta.")
    raw = payload.get("csv")
    if not isinstance(raw, str) or len(raw) > 1_000_000: raise HTTPException(413, "CSV inválido ou superior a 1 MB.")
    try:
        reader = csv.DictReader(io.StringIO(raw.lstrip("\ufeff")))
        if not reader.fieldnames or not {"contact_type", "full_name"}.issubset(set(reader.fieldnames)): raise HTTPException(422, "O CSV tem de incluir contact_type e full_name.")
        created = skipped = 0
        for row in reader:
            kind, name = (row.get("contact_type") or "").strip().lower(), (row.get("full_name") or "").strip()
            if kind not in {"owner", "client"} or len(name) < 2: skipped += 1; continue
            email = (row.get("email") or "").strip().lower() or None
            duplicate = db.scalar(_scope(select(Contact).where(Contact.contact_type == kind, Contact.full_name.ilike(name)), user))
            if duplicate or (email and db.scalar(_scope(select(Contact).where(Contact.email == email, Contact.contact_type == kind), user))): skipped += 1; continue
            contact = Contact(contact_type=kind, full_name=name[:160], email=email, phone=(row.get("phone") or "").strip() or None,
                municipality=(row.get("municipality") or "").strip() or None, district=(row.get("district") or "").strip() or None,
                property_preferences=(row.get("property_preferences") or "").strip() or None, source=(row.get("source") or "").strip() or "CSV import",
                lawful_basis=(row.get("lawful_basis") or "").strip() or None,
                contact_permission=(row.get("contact_permission") or "").strip().lower() in {"1","true","yes","sim"},
                do_not_contact=(row.get("do_not_contact") or "").strip().lower() in {"1","true","yes","sim"},
                assigned_to=user.id if user.role not in {UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.MANAGER} else None, created_by=user.id)
            db.add(contact); created += 1
        _audit(db, user, "contacts.imported", "batch", {"created": created, "skipped": skipped}); db.commit()
        return {"created": created, "skipped": skipped}
    except HTTPException: raise
    except Exception as exc:
        db.rollback(); raise HTTPException(422, f"Não foi possível importar o CSV ({type(exc).__name__}).")


@router.post("/import/update")
def update_contacts_from_csv(payload: dict, db: Session = Depends(get_db), user: User = Depends(get_business_user)):
    """Fill empty fields on uniquely matched contacts; never insert or overwrite populated values."""
    if user.role == UserRole.VIEWER:
        raise HTTPException(403, "A conta tem acesso apenas de consulta.")
    raw = payload.get("csv")
    if not isinstance(raw, str) or len(raw) > 1_000_000:
        raise HTTPException(413, "CSV inválido ou superior a 1 MB.")
    try:
        reader = csv.DictReader(io.StringIO(raw.lstrip("\ufeff")))
        required = {"contact_type", "full_name"}
        fields = {"email": 320, "phone": 80, "municipality": 120, "district": 120, "property_preferences": 2000, "source": 500}
        if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
            raise HTTPException(422, "O CSV tem de incluir contact_type e full_name.")
        if not (set(fields) & set(reader.fieldnames)):
            raise HTTPException(422, "Inclui pelo menos um campo para atualizar.")
        updated = unchanged = not_found = ambiguous = invalid = 0
        for row in reader:
            kind = (row.get("contact_type") or "").strip().lower()
            name = (row.get("full_name") or "").strip()
            if kind not in {"owner", "client"} or len(name) < 2:
                invalid += 1
                continue
            matches = db.scalars(_scope(select(Contact).where(Contact.contact_type == kind, Contact.full_name.ilike(name)), user)).all()
            if not matches:
                not_found += 1
                continue
            if len(matches) != 1:
                ambiguous += 1
                continue
            contact = matches[0]
            changed = False
            for field, limit in fields.items():
                value = (row.get(field) or "").strip()
                if not value or getattr(contact, field):
                    continue
                value = value[:limit].lower() if field == "email" else value[:limit]
                setattr(contact, field, value)
                changed = True
            if changed:
                updated += 1
            else:
                unchanged += 1
        _audit(db, user, "contacts.enriched", "batch", {"updated": updated, "unchanged": unchanged, "not_found": not_found, "ambiguous": ambiguous, "invalid": invalid})
        db.commit()
        return {"updated": updated, "unchanged": unchanged, "not_found": not_found, "ambiguous": ambiguous, "invalid": invalid}
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(422, f"Não foi possível atualizar os contactos ({type(exc).__name__}).")

@router.post("/agent-audience")
def get_agent_audience(payload: dict, db: Session = Depends(get_db), user: User = Depends(get_business_user)):
    ids = payload.get("contact_ids", [])
    if not isinstance(ids, list) or len(ids) > 200 or any(not isinstance(i, int) for i in ids): raise HTTPException(422, "contact_ids deve conter até 200 identificadores.")
    rows = db.scalars(_scope(select(Contact).where(Contact.id.in_(ids), Contact.active.is_(True), Contact.do_not_contact.is_(False)), user)).all() if ids else []
    # Only non-identifying property criteria are returned; names, emails and phones never reach the model.
    return {"count": len(rows), "audience": [{"type": x.contact_type, "municipality": x.municipality, "district": x.district, "preferences": x.property_preferences, "budget_min": x.budget_min, "budget_max": x.budget_max} for x in rows],
            "outreach_ready_count": sum(bool(x.contact_permission and x.lawful_basis and (x.email or x.phone)) for x in rows), "requires_human_approval": True, "messages_sent": 0}
