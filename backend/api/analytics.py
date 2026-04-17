"""Analytics API — add, list, summary."""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

try:
    from ..database import get_db, Persona, Content, Analytics
    from ..schemas import AnalyticsEntry, AnalyticsOut, AnalyticsSummary
except ImportError:
    from database import get_db, Persona, Content, Analytics
    from schemas import AnalyticsEntry, AnalyticsOut, AnalyticsSummary

router = APIRouter(tags=["analytics"])


@router.post("/analytics/", response_model=AnalyticsOut)
def add_analytics(body: AnalyticsEntry, db: Session = Depends(get_db)):
    entry = Analytics(
        persona_id=body.persona_id,
        date=body.date,
        platform=body.platform,
        subscribers=body.subscribers,
        revenue=body.revenue,
        tips=body.tips,
        messages_count=body.messages_count,
        likes=body.likes,
        views=body.views,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.get("/analytics/", response_model=List[AnalyticsOut])
def list_analytics(
    persona_id: Optional[int] = None,
    platform: Optional[str] = None,
    db: Session = Depends(get_db),
):
    q = db.query(Analytics)
    if persona_id:
        q = q.filter(Analytics.persona_id == persona_id)
    if platform:
        q = q.filter(Analytics.platform == platform)
    return q.order_by(Analytics.date.desc()).limit(200).all()


@router.get("/analytics/summary", response_model=AnalyticsSummary)
def analytics_summary(db: Session = Depends(get_db)):
    total_revenue = db.query(func.sum(Analytics.revenue)).scalar() or 0.0
    total_tips = db.query(func.sum(Analytics.tips)).scalar() or 0.0
    total_subs = db.query(func.max(Analytics.subscribers)).scalar() or 0
    total_content = db.query(Content).filter(Content.status == "completed").count()

    by_platform = {}
    platforms = db.query(Analytics.platform).distinct().all()
    for (plat,) in platforms:
        rev = db.query(func.sum(Analytics.revenue)).filter(Analytics.platform == plat).scalar() or 0
        tips = db.query(func.sum(Analytics.tips)).filter(Analytics.platform == plat).scalar() or 0
        subs = db.query(func.max(Analytics.subscribers)).filter(Analytics.platform == plat).scalar() or 0
        by_platform[plat] = {"revenue": rev, "tips": tips, "subscribers": subs}

    by_persona = []
    persona_ids = db.query(Analytics.persona_id).distinct().all()
    for (pid,) in persona_ids:
        persona = db.query(Persona).filter(Persona.id == pid).first()
        rev = db.query(func.sum(Analytics.revenue)).filter(Analytics.persona_id == pid).scalar() or 0
        content_count = db.query(Content).filter(Content.persona_id == pid, Content.status == "completed").count()
        by_persona.append({"persona_id": pid, "name": persona.name if persona else f"#{pid}", "revenue": rev, "content_count": content_count})

    by_persona.sort(key=lambda x: x["revenue"], reverse=True)
    top_persona = by_persona[0]["name"] if by_persona else None

    return AnalyticsSummary(
        total_revenue=total_revenue,
        total_tips=total_tips,
        total_subscribers=total_subs,
        total_content=total_content,
        top_persona=top_persona,
        by_platform=by_platform,
        by_persona=by_persona,
    )
