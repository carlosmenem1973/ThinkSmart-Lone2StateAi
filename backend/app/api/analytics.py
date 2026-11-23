from datetime import datetime, timedelta, timezone
from typing import Literal
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select, distinct
from sqlalchemy.orm import Session
from app.core.auth import get_business_user, require_admin_user
from app.core.database import get_db
from app.models.analytics import UsageEvent
from app.models.entities import User

router = APIRouter(prefix="/analytics", tags=["Analytics"])

class UsageEventInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_type: Literal["session_start", "page_view", "feature_action"]
    feature: Literal["dashboard", "procura", "agents", "contact_ai", "team", "settings", "other"]
    route: str | None = Field(default=None, max_length=120, pattern=r"^/[a-zA-Z0-9_./-]*$")
    session_id: str = Field(min_length=8, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")

@router.post("/events", status_code=202)
def record_usage_event(payload: UsageEventInput, user: User = Depends(get_business_user), db: Session = Depends(get_db)):
    db.add(UsageEvent(user_id=user.id, event_type=payload.event_type, feature=payload.feature,
                      route=payload.route, session_id=payload.session_id))
    db.commit()
    return {"accepted": True}

@router.get("/overview")
def analytics_overview(days: int = Query(default=30, ge=1, le=90),
                       _admin: User = Depends(require_admin_user), db: Session = Depends(get_db)):
    since = datetime.now(timezone.utc) - timedelta(days=days)
    event_filter = UsageEvent.created_at >= since
    active_today_since = datetime.now(timezone.utc) - timedelta(hours=24)
    total_users = db.scalar(select(func.count()).select_from(User).where(User.active.is_(True))) or 0
    active_users = db.scalar(select(func.count(distinct(UsageEvent.user_id))).where(event_filter)) or 0
    active_today = db.scalar(select(func.count(distinct(UsageEvent.user_id))).where(UsageEvent.created_at >= active_today_since)) or 0
    event_count = db.scalar(select(func.count()).select_from(UsageEvent).where(event_filter)) or 0
    sessions = db.scalar(select(func.count(distinct(UsageEvent.session_id))).where(event_filter, UsageEvent.event_type == "session_start")) or 0
    feature_rows = db.execute(select(UsageEvent.feature, func.count()).where(event_filter, UsageEvent.event_type.in_(["page_view", "feature_action"])).group_by(UsageEvent.feature).order_by(func.count().desc())).all()
    user_rows = db.execute(
        select(User.id, User.full_name, User.email, User.role, func.max(UsageEvent.created_at).label("last_active"),
               func.count(UsageEvent.id).label("events"))
        .join(UsageEvent, UsageEvent.user_id == User.id)
        .where(event_filter)
        .group_by(User.id, User.full_name, User.email, User.role)
        .order_by(func.max(UsageEvent.created_at).desc())
        .limit(100)
    ).all()
    return {
        "period_days": days, "active_users": active_users, "active_today": active_today,
        "total_users": total_users, "inactive_users": max(total_users - active_users, 0),
        "events": event_count, "sessions": sessions,
        "features": [{"feature": row[0], "events": row[1]} for row in feature_rows],
        "users": [{"id": row.id, "name": row.full_name, "email": row.email, "role": row.role.value,
                   "last_active": row.last_active.isoformat() if row.last_active else None, "events": row.events}
                  for row in user_rows],
    }
