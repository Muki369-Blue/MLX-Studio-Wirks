"""Async job queue worker.

Polls for QUEUED generation_jobs and dispatches them. Runs as a
background thread alongside the main FastAPI process.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone

from backend.database import (
    SessionLocal,
    GenerationJob,
    JobState,
    Content,
    Persona,
    CampaignTask,
)
from backend.services import jobs as jobs_service

logger = logging.getLogger(__name__)

_worker_thread = None
_stop_event = threading.Event()
POLL_INTERVAL = 5  # seconds


def _worker_loop():
    logger.info("Job queue worker started")
    while not _stop_event.is_set():
        try:
            db = SessionLocal()
            # Fetch highest-priority QUEUED job
            job = (
                db.query(GenerationJob)
                .filter(GenerationJob.status == JobState.QUEUED.value)
                .order_by(GenerationJob.priority.desc(), GenerationJob.created_at.asc())
                .first()
            )
            if job:
                _process_job(db, job)
            db.close()
        except Exception as e:
            logger.error("Worker loop error: %s", e)
        _stop_event.wait(POLL_INTERVAL)
    logger.info("Job queue worker stopped")


def _process_job(db, job: GenerationJob):
    """Dispatch a single job based on its type."""
    logger.info("Processing job %d (type=%s)", job.id, job.job_type)
    jobs_service.transition(db, job, JobState.DISPATCHING, actor="worker")
    db.commit()

    try:
        if job.job_type == "score":
            _run_scoring_job(db, job)
        elif job.job_type == "caption":
            _run_caption_job(db, job)
        elif job.job_type == "plan":
            _run_plan_job(db, job)
        elif job.job_type in ("image", "video"):
            # Image/video jobs are dispatched directly via ComfyUI in the router;
            # the worker only handles async re-dispatch for retries or campaign tasks
            _run_generation_job(db, job)
        else:
            logger.warning("Unknown job type: %s", job.job_type)
            jobs_service.transition(db, job, JobState.FAILED, error=f"Unknown job type: {job.job_type}", actor="worker")
            db.commit()
    except Exception as e:
        logger.error("Job %d failed: %s", job.id, e)
        jobs_service.transition(db, job, JobState.FAILED, error=str(e), actor="worker")
        db.commit()


def _run_scoring_job(db, job: GenerationJob):
    from backend.workers.scoring import score_content

    content = db.query(Content).filter(Content.id == job.content_id).first()
    if not content:
        jobs_service.transition(db, job, JobState.FAILED, error="Content not found", actor="worker")
        db.commit()
        return

    persona = db.query(Persona).filter(Persona.id == content.persona_id).first() if content.persona_id else None
    jobs_service.transition(db, job, JobState.RUNNING, actor="worker")
    db.commit()

    score = score_content(db, content, persona_description=persona.prompt_base if persona else None)

    jobs_service.transition(db, job, JobState.NEEDS_REVIEW if score.verdict == "needs_review" else JobState.APPROVED, actor="worker")
    db.commit()


def _run_caption_job(db, job: GenerationJob):
    from backend.services import llm as llm_service

    payload = job.payload or {}
    content = db.query(Content).filter(Content.id == job.content_id).first()
    if not content:
        jobs_service.transition(db, job, JobState.FAILED, error="Content not found", actor="worker")
        db.commit()
        return

    persona = db.query(Persona).filter(Persona.id == content.persona_id).first() if content.persona_id else None
    jobs_service.transition(db, job, JobState.RUNNING, actor="worker")
    db.commit()

    result = llm_service.generate_caption(
        content.prompt_used,
        persona_name=persona.name if persona else "Unknown",
        platform=payload.get("platform", "onlyfans"),
    )
    content.caption = result["caption"]
    content.hashtags = result["hashtags"]
    jobs_service.transition(db, job, JobState.APPROVED, actor="worker")
    db.commit()


def _run_plan_job(db, job: GenerationJob):
    """Planner agent job — generates a campaign plan."""
    from backend.services import agents

    jobs_service.transition(db, job, JobState.RUNNING, actor="worker")
    db.commit()

    try:
        agents.run_planner(db, job)
        jobs_service.transition(db, job, JobState.APPROVED, actor="worker")
    except Exception as e:
        jobs_service.transition(db, job, JobState.FAILED, error=str(e), actor="worker")
    db.commit()


def _run_generation_job(db, job: GenerationJob):
    """For campaign-dispatched image/video jobs — re-dispatch via ComfyUI."""
    # This is a placeholder; the actual ComfyUI dispatch happens in the routers.
    # Campaign jobs that arrive here need to be forwarded.
    jobs_service.transition(db, job, JobState.RUNNING, actor="worker")
    db.commit()
    logger.info("Generation job %d requires ComfyUI dispatch (not yet implemented in async worker)", job.id)


def start_worker():
    global _worker_thread
    if _worker_thread is not None and _worker_thread.is_alive():
        return
    _stop_event.clear()
    _worker_thread = threading.Thread(target=_worker_loop, daemon=True, name="empire-job-worker")
    _worker_thread.start()


def stop_worker():
    _stop_event.set()
    if _worker_thread is not None:
        _worker_thread.join(timeout=5)
