from celery import Celery
from app.core.config import settings

celery = Celery(
    "estateai",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.workers.tasks", "app.workers.contact_ai_tasks", "app.workers.communication_tasks"],
)
celery.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone=settings.timezone,
    enable_utc=True,
    beat_schedule={
        # Property discovery is the only recurring web-search schedule. It is
        # gated by the administrator-controlled search_enabled setting.
        "property-discovery-scheduler": {
            "task": "app.workers.contact_ai_tasks.run_scheduled_property_discovery",
            "schedule": 300.0,
        },
        "contact-ai-every-30-minutes": {
            "task": "app.workers.contact_ai_tasks.process_contact_queue",
            "schedule": 1800.0,
        },
        "communications-outbox-relay": {
            "task": "app.workers.communication_tasks.publish_pending_outbox",
            "schedule": 5.0,
        },
        "communications-sqs-consumer": {
            "task": "app.workers.communication_tasks.consume_sqs_messages",
            "schedule": 5.0,
        },
    },
)
