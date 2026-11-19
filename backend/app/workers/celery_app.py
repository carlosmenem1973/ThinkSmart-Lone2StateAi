from celery import Celery
from app.core.config import settings

celery = Celery(
    "estateai",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.workers.tasks", "app.workers.contact_ai_tasks"],
)
celery.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone=settings.timezone,
    enable_utc=True,
    beat_schedule={
        "daily-lead-research": {
            "task": "app.workers.tasks.daily_research",
            "schedule": 86400.0,
        },
        "property-discovery-scheduler": {\n            "task": "app.workers.contact_ai_tasks.run_scheduled_property_discovery",\n            "schedule": 300.0,\n        },\n        "contact-ai-every-30-minutes": {
            "task": "app.workers.contact_ai_tasks.process_contact_queue",
            "schedule": 1800.0,
        },
    },
)
