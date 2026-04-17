"""Jobs API — CRUD + events for generation jobs."""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.database import (
    get_db,
    GenerationJob,
    GenerationRun,
    EventLog,
    JobState,
    TERMINAL_JOB_STATES,
)
from backend.schemas import JobOut, JobCancel, EventLogOut
from backend.services import jobs as jobs_service

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/", response_model=List[JobOut])
def list_jobs(
    status: Optional[str] = None,
    job_type: Optional[str] = None,
    persona_id: Optional[int] = None,
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
):
    q = db.query(GenerationJob)
    if status:
        q = q.filter(GenerationJob.status == status)
    if job_type:
        q = q.filter(GenerationJob.job_type == job_type)
    if persona_id:
        q = q.filter(GenerationJob.persona_id == persona_id)
    return q.order_by(GenerationJob.id.desc()).limit(limit).all()


@router.get("/stats")
def job_stats(db: Session = Depends(get_db)):
    """Queue depth, running count, failure count."""
    from sqlalchemy import func

    queued = db.query(func.count(GenerationJob.id)).filter(GenerationJob.status == JobState.QUEUED.value).scalar()
    running = db.query(func.count(GenerationJob.id)).filter(GenerationJob.status.in_([JobState.DISPATCHING.value, JobState.RUNNING.value])).scalar()
    failed = db.query(func.count(GenerationJob.id)).filter(GenerationJob.status == JobState.FAILED.value).scalar()
    review = db.query(func.count(GenerationJob.id)).filter(GenerationJob.status == JobState.NEEDS_REVIEW.value).scalar()
    total = db.query(func.count(GenerationJob.id)).scalar()

    return {
        "queued": queued,
        "running": running,
        "failed": failed,
        "needs_review": review,
        "total": total,
    }


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = db.query(GenerationJob).filter(GenerationJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/{job_id}/cancel", response_model=JobOut)
def cancel_job(job_id: int, body: JobCancel = None, db: Session = Depends(get_db)):
    job = db.query(GenerationJob).filter(GenerationJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if jobs_service.is_terminal(job):
        raise HTTPException(status_code=409, detail="Job already in terminal state")

    jobs_service.transition(
        db, job, JobState.CANCELLED,
        actor="user",
        note=body.reason if body else None,
    )
    db.commit()
    return job


@router.get("/{job_id}/events", response_model=List[EventLogOut])
def job_events(job_id: int, db: Session = Depends(get_db)):
    """All events for a specific job."""
    return (
        db.query(EventLog)
        .filter(EventLog.subject_type == "generation_job", EventLog.subject_id == job_id)
        .order_by(EventLog.id.asc())
        .all()
    )


@router.get("/{job_id}/runs")
def job_runs(job_id: int, db: Session = Depends(get_db)):
    """All execution runs for a job."""
    runs = (
        db.query(GenerationRun)
        .filter(GenerationRun.job_id == job_id)
        .order_by(GenerationRun.attempt.asc())
        .all()
    )
    return [
        {
            "id": r.id,
            "attempt": r.attempt,
            "prompt": r.prompt,
            "backend": r.backend,
            "machine": r.machine,
            "status": r.status,
            "duration_seconds": r.duration_seconds,
            "output_path": r.output_path,
            "error": r.error,
            "started_at": r.started_at,
            "finished_at": r.finished_at,
        }
        for r in runs
    ]
