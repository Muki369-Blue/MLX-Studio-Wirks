"""Schedules API — content calendar + post queue."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

try:
    from ..database import get_db, Persona, Content, Schedule, PostQueue
    from ..schemas import ScheduleCreate, ScheduleOut, PostQueueCreate, PostQueueOut
except ImportError:
    from database import get_db, Persona, Content, Schedule, PostQueue
    from schemas import ScheduleCreate, ScheduleOut, PostQueueCreate, PostQueueOut

router = APIRouter(tags=["schedules"])


@router.post("/schedules/", response_model=ScheduleOut)
def create_schedule(body: ScheduleCreate, db: Session = Depends(get_db)):
    persona = db.query(Persona).filter(Persona.id == body.persona_id).first()
    if not persona:
        raise HTTPException(status_code=404, detail="Persona not found")
    try:
        from ..scheduler import _next_run
    except ImportError:
        from scheduler import _next_run
    sched = Schedule(
        persona_id=body.persona_id,
        prompt_template=body.prompt_template,
        cron_expression=body.cron_expression,
        batch_size=body.batch_size,
        next_run=_next_run(body.cron_expression),
    )
    db.add(sched)
    db.commit()
    db.refresh(sched)
    return sched


@router.get("/schedules/", response_model=List[ScheduleOut])
def list_schedules(db: Session = Depends(get_db)):
    return db.query(Schedule).order_by(Schedule.id.desc()).all()


@router.patch("/schedules/{schedule_id}/toggle")
def toggle_schedule(schedule_id: int, db: Session = Depends(get_db)):
    sched = db.query(Schedule).filter(Schedule.id == schedule_id).first()
    if not sched:
        raise HTTPException(status_code=404, detail="Schedule not found")
    sched.enabled = not sched.enabled
    db.commit()
    return {"id": schedule_id, "enabled": sched.enabled}


@router.delete("/schedules/{schedule_id}")
def delete_schedule(schedule_id: int, db: Session = Depends(get_db)):
    sched = db.query(Schedule).filter(Schedule.id == schedule_id).first()
    if not sched:
        raise HTTPException(status_code=404, detail="Schedule not found")
    db.delete(sched)
    db.commit()
    return {"status": "deleted"}


# ── Post Queue ───────────────────────────────────────────────────────

@router.post("/post-queue/", response_model=PostQueueOut)
def queue_post(body: PostQueueCreate, db: Session = Depends(get_db)):
    content = db.query(Content).filter(Content.id == body.content_id).first()
    if not content:
        raise HTTPException(status_code=404, detail="Content not found")
    post = PostQueue(content_id=body.content_id, platform=body.platform, caption=body.caption, scheduled_at=body.scheduled_at)
    db.add(post)
    db.commit()
    db.refresh(post)
    return post


@router.get("/post-queue/", response_model=List[PostQueueOut])
def list_post_queue(db: Session = Depends(get_db)):
    return db.query(PostQueue).order_by(PostQueue.id.desc()).limit(100).all()


@router.post("/post-queue/{post_id}/post-now")
def post_now(post_id: int, db: Session = Depends(get_db)):
    post = db.query(PostQueue).filter(PostQueue.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    content = db.query(Content).filter(Content.id == post.content_id).first()
    post.status = "posted"
    post.posted_at = datetime.now(timezone.utc)
    db.commit()
    if content:
        platforms = set((content.posted_platforms or "").split(",")) if content.posted_platforms else set()
        platforms.discard("")
        platforms.add(post.platform)
        content.posted_platforms = ",".join(platforms)
        content.is_posted = True
        db.commit()
    return {"status": "posted", "platform": post.platform}


@router.delete("/post-queue/{post_id}")
def delete_post(post_id: int, db: Session = Depends(get_db)):
    post = db.query(PostQueue).filter(PostQueue.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    db.delete(post)
    db.commit()
    return {"status": "deleted"}
