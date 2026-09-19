"""Celery application configuration and baseline worker tasks."""

from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "document_intelligence",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.workers.tasks.document_processing"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_track_started=True,
    result_expires=3600,
    worker_concurrency=settings.CELERY_WORKER_CONCURRENCY,
)


@celery_app.task(name="health_check_task")
def health_check_task() -> dict[str, str]:
    """Baseline test task to verify Celery broker and worker connectivity."""
    return {"status": "ok"}
