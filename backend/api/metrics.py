"""Metrics API — content, persona, campaign, and cost metrics CRUD + summaries."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

try:
    from ..database import (
        get_db,
        ContentMetrics,
        PersonaMetricsDaily,
        CampaignMetrics,
        GenerationCostMetrics,
    )
    from ..schemas import (
        ContentMetricsIn, ContentMetricsOut,
        PersonaMetricsDailyIn, PersonaMetricsDailyOut,
        CampaignMetricsIn, CampaignMetricsOut,
        GenerationCostIn, GenerationCostOut,
    )
except ImportError:
    from database import (
        get_db,
        ContentMetrics,
        PersonaMetricsDaily,
        CampaignMetrics,
        GenerationCostMetrics,
    )
    from schemas import (
        ContentMetricsIn, ContentMetricsOut,
        PersonaMetricsDailyIn, PersonaMetricsDailyOut,
        CampaignMetricsIn, CampaignMetricsOut,
        GenerationCostIn, GenerationCostOut,
    )

router = APIRouter(tags=["metrics"])

# ── Content Metrics ──────────────────────────────────────────────────

@router.post("/metrics/content", response_model=ContentMetricsOut)
def add_content_metrics(body: ContentMetricsIn, db: Session = Depends(get_db)):
    row = ContentMetrics(**body.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.get("/metrics/content/{content_id}", response_model=List[ContentMetricsOut])
def get_content_metrics(content_id: int, db: Session = Depends(get_db)):
    return (
        db.query(ContentMetrics)
        .filter(ContentMetrics.content_id == content_id)
        .order_by(ContentMetrics.collected_at.desc())
        .all()
    )


@router.get("/metrics/content-summary")
def content_metrics_summary(
    platform: Optional[str] = None,
    db: Session = Depends(get_db),
):
    q = db.query(ContentMetrics)
    if platform:
        q = q.filter(ContentMetrics.platform == platform)
    rows = q.all()
    if not rows:
        return {"total_views": 0, "total_likes": 0, "total_comments": 0, "total_tips": 0.0, "total_unlocks": 0, "count": 0}
    return {
        "total_views": sum(r.views or 0 for r in rows),
        "total_likes": sum(r.likes or 0 for r in rows),
        "total_comments": sum(r.comments or 0 for r in rows),
        "total_tips": round(sum(r.tips or 0 for r in rows), 2),
        "total_unlocks": sum(r.unlocks or 0 for r in rows),
        "count": len(rows),
    }


# ── Persona Daily Metrics ────────────────────────────────────────────

@router.post("/metrics/persona", response_model=PersonaMetricsDailyOut)
def add_persona_metrics(body: PersonaMetricsDailyIn, db: Session = Depends(get_db)):
    # Upsert: if a row exists for the same persona+date+platform, update it
    existing = (
        db.query(PersonaMetricsDaily)
        .filter(
            PersonaMetricsDaily.persona_id == body.persona_id,
            PersonaMetricsDaily.date == body.date,
            PersonaMetricsDaily.platform == body.platform,
        )
        .first()
    )
    if existing:
        for k, v in body.model_dump(exclude={"persona_id", "date", "platform"}).items():
            setattr(existing, k, v)
        db.commit()
        db.refresh(existing)
        return existing
    row = PersonaMetricsDaily(**body.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.get("/metrics/persona/{persona_id}", response_model=List[PersonaMetricsDailyOut])
def get_persona_metrics(
    persona_id: int,
    platform: Optional[str] = None,
    limit: int = Query(30, le=365),
    db: Session = Depends(get_db),
):
    q = db.query(PersonaMetricsDaily).filter(PersonaMetricsDaily.persona_id == persona_id)
    if platform:
        q = q.filter(PersonaMetricsDaily.platform == platform)
    return q.order_by(PersonaMetricsDaily.date.desc()).limit(limit).all()


@router.get("/metrics/persona-summary/{persona_id}")
def persona_metrics_summary(persona_id: int, db: Session = Depends(get_db)):
    rows = db.query(PersonaMetricsDaily).filter(PersonaMetricsDaily.persona_id == persona_id).all()
    if not rows:
        return {"total_revenue": 0.0, "total_tips": 0.0, "net_subscribers": 0, "total_content_posted": 0, "days_tracked": 0}
    return {
        "total_revenue": round(sum(r.revenue or 0 for r in rows), 2),
        "total_tips": round(sum(r.tips or 0 for r in rows), 2),
        "net_subscribers": sum((r.new_subscribers or 0) - (r.churned_subscribers or 0) for r in rows),
        "total_content_posted": sum(r.content_posted or 0 for r in rows),
        "days_tracked": len(rows),
    }


# ── Campaign Metrics ─────────────────────────────────────────────────

@router.post("/metrics/campaign", response_model=CampaignMetricsOut)
def add_campaign_metrics(body: CampaignMetricsIn, db: Session = Depends(get_db)):
    row = CampaignMetrics(**body.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.get("/metrics/campaign/{campaign_id}", response_model=List[CampaignMetricsOut])
def get_campaign_metrics(campaign_id: int, db: Session = Depends(get_db)):
    return (
        db.query(CampaignMetrics)
        .filter(CampaignMetrics.campaign_id == campaign_id)
        .order_by(CampaignMetrics.day.asc())
        .all()
    )


@router.get("/metrics/campaign-summary/{campaign_id}")
def campaign_metrics_summary(campaign_id: int, db: Session = Depends(get_db)):
    rows = db.query(CampaignMetrics).filter(CampaignMetrics.campaign_id == campaign_id).all()
    if not rows:
        return {"total_produced": 0, "total_approved": 0, "total_posted": 0, "total_revenue": 0.0, "days_tracked": 0}
    return {
        "total_produced": sum(r.content_produced or 0 for r in rows),
        "total_approved": sum(r.content_approved or 0 for r in rows),
        "total_posted": sum(r.content_posted or 0 for r in rows),
        "total_revenue": round(sum(r.revenue_attributed or 0 for r in rows), 2),
        "days_tracked": len(rows),
    }


# ── Generation Cost Metrics ──────────────────────────────────────────

@router.post("/metrics/cost", response_model=GenerationCostOut)
def add_cost_metrics(body: GenerationCostIn, db: Session = Depends(get_db)):
    row = GenerationCostMetrics(**body.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.get("/metrics/cost", response_model=List[GenerationCostOut])
def list_cost_metrics(
    machine: Optional[str] = None,
    job_type: Optional[str] = None,
    limit: int = Query(50, le=500),
    db: Session = Depends(get_db),
):
    q = db.query(GenerationCostMetrics)
    if machine:
        q = q.filter(GenerationCostMetrics.machine == machine)
    if job_type:
        q = q.filter(GenerationCostMetrics.job_type == job_type)
    return q.order_by(GenerationCostMetrics.created_at.desc()).limit(limit).all()


@router.get("/metrics/cost-summary")
def cost_metrics_summary(db: Session = Depends(get_db)):
    rows = db.query(GenerationCostMetrics).all()
    if not rows:
        return {"total_cost_usd": 0.0, "total_jobs": 0, "avg_duration_seconds": 0.0, "by_machine": {}, "by_type": {}}

    by_machine: dict = {}
    by_type: dict = {}
    durations = []
    for r in rows:
        m = r.machine or "unknown"
        t = r.job_type or "unknown"
        by_machine.setdefault(m, {"count": 0, "cost": 0.0})
        by_machine[m]["count"] += 1
        by_machine[m]["cost"] = round(by_machine[m]["cost"] + (r.estimated_cost_usd or 0), 4)
        by_type.setdefault(t, {"count": 0, "cost": 0.0})
        by_type[t]["count"] += 1
        by_type[t]["cost"] = round(by_type[t]["cost"] + (r.estimated_cost_usd or 0), 4)
        if r.duration_seconds:
            durations.append(r.duration_seconds)

    return {
        "total_cost_usd": round(sum(r.estimated_cost_usd or 0 for r in rows), 4),
        "total_jobs": len(rows),
        "avg_duration_seconds": round(sum(durations) / len(durations), 1) if durations else 0.0,
        "by_machine": by_machine,
        "by_type": by_type,
    }
