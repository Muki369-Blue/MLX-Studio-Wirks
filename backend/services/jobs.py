"""Job lifecycle helpers.

Every image/video/scoring/analytics task is represented by a GenerationJob
row. State transitions flow through `transition()` so the event_log always
has an audit entry. Per-attempt execution detail lives in generation_runs.

Callers:
  - current /generate, /generate-video endpoints (Phase 1.5 wiring)
  - future orchestrator (Phase 2)
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from backend.database import (
    EventLog,
    GenerationJob,
    GenerationRun,
    JobState,
    TERMINAL_JOB_STATES,
)


def log_event(
    db: Session,
    *,
    event_type: str,
    subject_type: Optional[str] = None,
    subject_id: Optional[int] = None,
    actor: str = "system",
    payload: Optional[dict[str, Any]] = None,
) -> EventLog:
    event = EventLog(
        event_type=event_type,
        subject_type=subject_type,
        subject_id=subject_id,
        actor=actor,
        payload=payload,
    )
    db.add(event)
    db.flush()
    return event


def create_job(
    db: Session,
    *,
    job_type: str,
    persona_id: Optional[int] = None,
    payload: Optional[dict[str, Any]] = None,
    content_id: Optional[int] = None,
    campaign_task_id: Optional[int] = None,
    machine: str = "mac",
    priority: int = 0,
    actor: str = "system",
) -> GenerationJob:
    job = GenerationJob(
        persona_id=persona_id,
        job_type=job_type,
        status=JobState.QUEUED.value,
        payload=payload,
        content_id=content_id,
        campaign_task_id=campaign_task_id,
        machine=machine,
        priority=priority,
    )
    db.add(job)
    db.flush()  # assign job.id
    log_event(
        db,
        event_type="job.created",
        subject_type="generation_job",
        subject_id=job.id,
        actor=actor,
        payload={"job_type": job_type, "persona_id": persona_id, "machine": machine},
    )
    return job


def transition(
    db: Session,
    job: GenerationJob,
    new_state: JobState,
    *,
    actor: str = "system",
    note: Optional[str] = None,
    error: Optional[str] = None,
) -> GenerationJob:
    """Move a job to a new state and record an event. No-op if already there."""
    new_value = new_state.value if isinstance(new_state, JobState) else str(new_state)
    if job.status == new_value:
        return job
    old = job.status
    job.status = new_value
    if error is not None:
        job.error = error
    job.updated_at = datetime.now(timezone.utc)
    log_event(
        db,
        event_type="job.state_change",
        subject_type="generation_job",
        subject_id=job.id,
        actor=actor,
        payload={
            "from": old,
            "to": new_value,
            "note": note,
            "error": error,
        },
    )
    return job


def record_run(
    db: Session,
    job: GenerationJob,
    *,
    prompt: Optional[str] = None,
    refined_prompt: Optional[str] = None,
    negative_prompt: Optional[str] = None,
    loras: Optional[list[dict[str, Any]]] = None,
    backend: Optional[str] = None,
    model: Optional[str] = None,
    seed: Optional[int] = None,
    width: Optional[int] = None,
    height: Optional[int] = None,
    machine: Optional[str] = None,
) -> GenerationRun:
    existing_attempts = len(job.runs) if job.runs is not None else 0
    run = GenerationRun(
        job_id=job.id,
        attempt=existing_attempts + 1,
        prompt=prompt,
        refined_prompt=refined_prompt,
        negative_prompt=negative_prompt,
        loras=loras,
        backend=backend,
        model=model,
        seed=seed,
        width=width,
        height=height,
        machine=machine or job.machine,
        status="running",
    )
    db.add(run)
    db.flush()
    return run


def finish_run(
    db: Session,
    run: GenerationRun,
    *,
    status: str = "completed",
    output_path: Optional[str] = None,
    preview_path: Optional[str] = None,
    duration_seconds: Optional[float] = None,
    error: Optional[str] = None,
) -> GenerationRun:
    run.status = status
    run.finished_at = datetime.now(timezone.utc)
    if output_path is not None:
        run.output_path = output_path
    if preview_path is not None:
        run.preview_path = preview_path
    if duration_seconds is not None:
        run.duration_seconds = duration_seconds
    if error is not None:
        run.error = error
    db.flush()
    return run


def is_terminal(job: GenerationJob) -> bool:
    try:
        return JobState(job.status) in TERMINAL_JOB_STATES
    except ValueError:
        return False


def job_for_content(db: Session, content_id: int) -> Optional[GenerationJob]:
    """Look up the most recent job that produced a given Content row."""
    return (
        db.query(GenerationJob)
        .filter(GenerationJob.content_id == content_id)
        .order_by(GenerationJob.id.desc())
        .first()
    )
