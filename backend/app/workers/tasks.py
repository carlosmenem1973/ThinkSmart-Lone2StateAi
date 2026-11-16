from app.workers.celery_app import celery
from app.services.ai import research_web
from app.core.database import SessionLocal
from app.models.entities import AuditLog

@celery.task(name="app.workers.tasks.daily_research")
def daily_research():
    query="Potential property sale opportunities in Portugal published in the last 7 days; focus on public sources and source URLs."
    result=research_web(query)
    db=SessionLocal()
    try:
        db.add(AuditLog(action="scheduled.research.completed",entity_type="research",entity_id=result.get("response_id","unknown"),details={"query":query,"report":result.get("text","")[:12000]})); db.commit()
    finally: db.close()
    return {"response_id":result.get("response_id"),"report":result.get("text","")}
