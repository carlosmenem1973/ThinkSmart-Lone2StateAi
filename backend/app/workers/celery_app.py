from celery import Celery
from app.core.config import settings
celery=Celery("estateai",broker=settings.redis_url,backend=settings.redis_url,include=["app.workers.tasks"])
celery.conf.update(task_serializer="json",accept_content=["json"],result_serializer="json",timezone=settings.timezone,enable_utc=True,beat_schedule={"daily-lead-research":{"task":"app.workers.tasks.daily_research","schedule":86400.0}})
