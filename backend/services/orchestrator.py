"""Orchestrator service — coordinates multi-step tasks and campaigns.

Task types:
  image, video, caption, score, plan, post, analytics

The orchestrator translates high-level campaign tasks into generation jobs
and manages dependencies between them.
"""
from __future__ import annotations

import enum
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from backend.database import (
    Campaign,
    CampaignTask,
    GenerationJob,
    JobState,
)
from backend.services import jobs as jobs_service

logger = logging.getLogger(__name__)


class TaskType(str, enum.Enum):
    IMAGE = "image"
    VIDEO = "video"
    CAPTION = "caption"
    SCORE = "score"
    PLAN = "plan"
    POST = "post"
    ANALYTICS = "analytics"


def create_campaign(
    db: Session,
    *,
    persona_id: int,
    name: str,
    description: str | None = None,
    total_days: int = 4,
    config: dict[str, Any] | None = None,
) -> Campaign:
    campaign = Campaign(
        persona_id=persona_id,
        name=name,
        description=description,
        total_days=total_days,
        config=config or {},
    )
    db.add(campaign)
    db.flush()
    jobs_service.log_event(
        db,
        event_type="campaign.created",
        subject_type="campaign",
        subject_id=campaign.id,
        actor="system",
        payload={"name": name, "persona_id": persona_id, "total_days": total_days},
    )
    return campaign


def add_task(
    db: Session,
    campaign: Campaign,
    *,
    day: int,
    task_type: str,
    config: dict[str, Any] | None = None,
    depends_on: list[int] | None = None,
    scheduled_at: datetime | None = None,
) -> CampaignTask:
    task = CampaignTask(
        campaign_id=campaign.id,
        day=day,
        task_type=task_type,
        config=config,
        depends_on=depends_on,
        scheduled_at=scheduled_at,
    )
    db.add(task)
    db.flush()
    return task


def start_campaign(db: Session, campaign: Campaign) -> Campaign:
    campaign.status = "active"
    campaign.current_day = 1
    campaign.started_at = datetime.now(timezone.utc)
    db.flush()
    jobs_service.log_event(
        db,
        event_type="campaign.started",
        subject_type="campaign",
        subject_id=campaign.id,
        actor="system",
    )
    # Queue all day-1 tasks
    _queue_day_tasks(db, campaign, day=1)
    return campaign


def _queue_day_tasks(db: Session, campaign: Campaign, day: int):
    """Queue all tasks for a given campaign day whose dependencies are met."""
    tasks = (
        db.query(CampaignTask)
        .filter(
            CampaignTask.campaign_id == campaign.id,
            CampaignTask.day == day,
            CampaignTask.status == "pending",
        )
        .all()
    )
    for task in tasks:
        if _deps_met(db, task):
            _dispatch_task(db, task, campaign)


def _deps_met(db: Session, task: CampaignTask) -> bool:
    if not task.depends_on:
        return True
    for dep_id in task.depends_on:
        dep = db.query(CampaignTask).filter(CampaignTask.id == dep_id).first()
        if not dep or dep.status != "completed":
            return False
    return True


def _dispatch_task(db: Session, task: CampaignTask, campaign: Campaign):
    """Create a GenerationJob for a campaign task and mark it queued."""
    job = jobs_service.create_job(
        db,
        job_type=task.task_type,
        persona_id=campaign.persona_id,
        campaign_task_id=task.id,
        payload=task.config,
        actor="orchestrator",
    )
    task.job_id = job.id
    task.status = "queued"
    task.started_at = datetime.now(timezone.utc)
    db.flush()


def on_task_completed(db: Session, task: CampaignTask):
    """Called when a campaign task finishes — checks if day is done, advances."""
    task.status = "completed"
    task.finished_at = datetime.now(timezone.utc)
    db.flush()

    campaign = task.campaign

    # Re-check pending tasks on the same day (dependency resolution)
    _queue_day_tasks(db, campaign, task.day)

    # Check if all tasks for current day are terminal
    day_tasks = (
        db.query(CampaignTask)
        .filter(CampaignTask.campaign_id == campaign.id, CampaignTask.day == task.day)
        .all()
    )
    if all(t.status in ("completed", "failed", "skipped") for t in day_tasks):
        _advance_day(db, campaign)


def _advance_day(db: Session, campaign: Campaign):
    next_day = campaign.current_day + 1
    if next_day > campaign.total_days:
        campaign.status = "completed"
        campaign.finished_at = datetime.now(timezone.utc)
        jobs_service.log_event(
            db,
            event_type="campaign.completed",
            subject_type="campaign",
            subject_id=campaign.id,
            actor="orchestrator",
        )
    else:
        campaign.current_day = next_day
        _queue_day_tasks(db, campaign, next_day)
        jobs_service.log_event(
            db,
            event_type="campaign.day_advanced",
            subject_type="campaign",
            subject_id=campaign.id,
            actor="orchestrator",
            payload={"day": next_day},
        )
    db.flush()


def cancel_campaign(db: Session, campaign: Campaign) -> Campaign:
    campaign.status = "cancelled"
    campaign.finished_at = datetime.now(timezone.utc)
    # Cancel all pending/queued tasks
    pending = (
        db.query(CampaignTask)
        .filter(
            CampaignTask.campaign_id == campaign.id,
            CampaignTask.status.in_(["pending", "queued"]),
        )
        .all()
    )
    for t in pending:
        t.status = "skipped"
    db.flush()
    jobs_service.log_event(
        db,
        event_type="campaign.cancelled",
        subject_type="campaign",
        subject_id=campaign.id,
        actor="system",
    )
    return campaign
