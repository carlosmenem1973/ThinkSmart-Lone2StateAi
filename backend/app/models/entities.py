import enum
from datetime import datetime, timezone
from sqlalchemy import String, Text, Integer, DateTime, Boolean, ForeignKey, JSON, Enum, UniqueConstraint, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base

def utcnow(): return datetime.now(timezone.utc)

class LeadStatus(str, enum.Enum): NEW="new"; REVIEW="review"; QUALIFIED="qualified"; CONTACTED="contacted"; REPLIED="replied"; LISTED="listed"; LOST="lost"; SUPPRESSED="suppressed"
class UserRole(str, enum.Enum): ADMIN="admin"; SELLER="seller"
class DraftStatus(str, enum.Enum): PENDING="pending"; APPROVED="approved"; REJECTED="rejected"; SENT="sent"

class User(Base):
    __tablename__="users"
    id: Mapped[int]=mapped_column(primary_key=True)
    email: Mapped[str]=mapped_column(String(320), unique=True, index=True)
    # Stable identity reference from the existing Amazon Cognito User Pool.
    cognito_sub: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True, index=True)
    full_name: Mapped[str]=mapped_column(String(160))
    role: Mapped[UserRole]=mapped_column(Enum(UserRole), default=UserRole.SELLER)
    territory: Mapped[str|None]=mapped_column(String(160), nullable=True)
    active: Mapped[bool]=mapped_column(Boolean, default=True)
    password_hash: Mapped[str|None]=mapped_column(String(500), nullable=True)
    must_change_password: Mapped[bool]=mapped_column(Boolean, default=True)
    failed_login_attempts: Mapped[int]=mapped_column(Integer, default=0)
    token_version: Mapped[int]=mapped_column(Integer, default=0)
    locked_until: Mapped[datetime|None]=mapped_column(DateTime(timezone=True), nullable=True)
    last_login_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=utcnow)

class Lead(Base):
    __tablename__="leads"
    id: Mapped[int]=mapped_column(primary_key=True)
    title: Mapped[str]=mapped_column(String(300))
    property_type: Mapped[str|None]=mapped_column(String(100), nullable=True)
    address: Mapped[str|None]=mapped_column(String(500), nullable=True)
    municipality: Mapped[str|None]=mapped_column(String(120), nullable=True)
    district: Mapped[str|None]=mapped_column(String(120), nullable=True)
    source_url: Mapped[str|None]=mapped_column(String(2000), nullable=True)
    source_name: Mapped[str|None]=mapped_column(String(200), nullable=True)
    evidence: Mapped[str|None]=mapped_column(Text, nullable=True)
    owner_name: Mapped[str|None]=mapped_column(String(200), nullable=True)
    owner_email: Mapped[str|None]=mapped_column(String(320), nullable=True)
    owner_phone: Mapped[str|None]=mapped_column(String(80), nullable=True)
    contact_confidence: Mapped[str]=mapped_column(String(20), default="unknown")
    contact_source: Mapped[str|None]=mapped_column(String(1000), nullable=True)
    lawful_basis: Mapped[str|None]=mapped_column(String(500), nullable=True)
    outreach_allowed: Mapped[bool]=mapped_column(Boolean, default=False)
    score: Mapped[int]=mapped_column(Integer, default=0)
    score_reason: Mapped[str|None]=mapped_column(Text, nullable=True)
    status: Mapped[LeadStatus]=mapped_column(Enum(LeadStatus), default=LeadStatus.NEW)
    assigned_to: Mapped[int|None]=mapped_column(ForeignKey("users.id"), nullable=True)
    property_data: Mapped[dict]=mapped_column(JSON, default=dict)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    seller = relationship("User")
    __table_args__=(UniqueConstraint("source_url", name="uq_lead_source_url"),)

class FollowUp(Base):
    __tablename__="followups"
    id: Mapped[int]=mapped_column(primary_key=True)
    lead_id: Mapped[int]=mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), index=True)
    seller_id: Mapped[int]=mapped_column(ForeignKey("users.id"))
    due_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), index=True)
    note: Mapped[str]=mapped_column(Text)
    completed: Mapped[bool]=mapped_column(Boolean, default=False)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=utcnow)
    lead=relationship("Lead"); seller=relationship("User")

class EmailInsight(Base):
    __tablename__="email_insights"
    id: Mapped[int]=mapped_column(primary_key=True)
    mailbox: Mapped[str]=mapped_column(String(320), index=True)
    graph_message_id: Mapped[str]=mapped_column(String(500), unique=True)
    subject: Mapped[str|None]=mapped_column(String(998), nullable=True)
    sender: Mapped[str|None]=mapped_column(String(320), nullable=True)
    received_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True), nullable=True)
    summary: Mapped[str|None]=mapped_column(Text, nullable=True)
    extracted_data: Mapped[dict]=mapped_column(JSON, default=dict)
    processed_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=utcnow)

class OutreachDraft(Base):
    __tablename__="outreach_drafts"
    id: Mapped[int]=mapped_column(primary_key=True)
    lead_id: Mapped[int]=mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), index=True)
    created_by: Mapped[int]=mapped_column(ForeignKey("users.id"))
    recipient: Mapped[str]=mapped_column(String(320))
    subject: Mapped[str]=mapped_column(String(998))
    body: Mapped[str]=mapped_column(Text)
    status: Mapped[DraftStatus]=mapped_column(Enum(DraftStatus), default=DraftStatus.PENDING)
    approved_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=utcnow)
    lead=relationship("Lead")

class AuditLog(Base):
    __tablename__="audit_logs"
    id: Mapped[int]=mapped_column(primary_key=True)
    actor_id: Mapped[int|None]=mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str]=mapped_column(String(120))
    entity_type: Mapped[str]=mapped_column(String(80))
    entity_id: Mapped[str]=mapped_column(String(80))
    details: Mapped[dict]=mapped_column(JSON, default=dict)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=utcnow)


class RefreshSession(Base):
    __tablename__="refresh_sessions"
    id: Mapped[int]=mapped_column(primary_key=True)
    user_id: Mapped[int]=mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str]=mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True), nullable=True)
    user_agent: Mapped[str|None]=mapped_column(String(500), nullable=True)
    ip_address: Mapped[str|None]=mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=utcnow)
    user=relationship("User")


class BrandSettings(Base):
    """Single-workspace branding, editable by administrators without redeploying."""
    __tablename__ = "brand_settings"
    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    product_name: Mapped[str] = mapped_column(String(100), default="ThinkSmart AI")
    customer_name: Mapped[str] = mapped_column(String(160), default="Loft2 Real Estate")
    tagline: Mapped[str] = mapped_column(String(240), default="Real Estate Intelligence")
    logo_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    primary_color: Mapped[str] = mapped_column(String(7), default="#2563EB")
    accent_color: Mapped[str] = mapped_column(String(7), default="#16866C")
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    __table_args__ = (CheckConstraint("id = 1", name="ck_brand_settings_singleton"),)
