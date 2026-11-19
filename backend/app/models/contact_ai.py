from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base

def utcnow():
    return datetime.now(timezone.utc)

class ContactAISettings(Base):
    __tablename__ = "contact_ai_settings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    mode: Mapped[str] = mapped_column(String(20), default="approval", nullable=False)
    interval_minutes: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    channel: Mapped[str] = mapped_column(String(20), default="website", nullable=False)
    paused_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    search_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    search_query: Mapped[str] = mapped_column(Text, default="Oportunidades imobiliárias publicadas recentemente em Portugal", nullable=False)
    search_interval_minutes: Mapped[int] = mapped_column(Integer, default=1440, nullable=False)
    last_search_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_search_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

class ContactConversation(Base):
    __tablename__ = "contact_conversations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    visitor_id: Mapped[str] = mapped_column(String(80), index=True)
    visitor_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    visitor_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    consent_to_followup: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="open", nullable=False, index=True)
    last_message_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class ContactMessage(Base):
    __tablename__ = "contact_messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("contact_conversations.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    delivery_status: Mapped[str] = mapped_column(String(20), default="received", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
