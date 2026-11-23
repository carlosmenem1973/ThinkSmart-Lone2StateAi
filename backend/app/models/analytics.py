from datetime import datetime, timezone
from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base

def utcnow():
    return datetime.now(timezone.utc)

class UsageEvent(Base):
    __tablename__ = "usage_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    feature: Mapped[str] = mapped_column(String(40), nullable=False)
    route: Mapped[str | None] = mapped_column(String(120), nullable=True)
    session_id: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

Index("ix_usage_events_created_at", UsageEvent.created_at)
Index("ix_usage_events_user_created", UsageEvent.user_id, UsageEvent.created_at)
Index("ix_usage_events_feature_created", UsageEvent.feature, UsageEvent.created_at)
