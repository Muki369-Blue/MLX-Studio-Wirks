"""Campaign API — create, start, cancel, list campaigns + tasks."""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.database import get_db, Campaign, CampaignTask, Persona
from backend.schemas import CampaignCreate, CampaignOut, CampaignTaskOut
from backend.services import orchestrator

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


@router.post("/", response_model=CampaignOut)
def create_campaign(body: CampaignCreate, db: Session = Depends(get_db)):
    persona = db.query(Persona).filter(Persona.id == body.persona_id).first()
    if not persona:
        raise HTTPException(status_code=404, detail="Persona not found")

    campaign = orchestrator.create_campaign(
        db,
        persona_id=body.persona_id,
        name=body.name,
        description=body.description,
        total_days=body.total_days,
        config=body.config,
    )
    db.commit()
    db.refresh(campaign)
    return campaign


@router.get("/", response_model=List[CampaignOut])
def list_campaigns(db: Session = Depends(get_db)):
    return db.query(Campaign).order_by(Campaign.id.desc()).limit(50).all()


@router.get("/{campaign_id}", response_model=CampaignOut)
def get_campaign(campaign_id: int, db: Session = Depends(get_db)):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign


@router.post("/{campaign_id}/start", response_model=CampaignOut)
def start_campaign(campaign_id: int, db: Session = Depends(get_db)):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if campaign.status != "draft":
        raise HTTPException(status_code=409, detail=f"Campaign is {campaign.status}, expected draft")

    orchestrator.start_campaign(db, campaign)
    db.commit()
    db.refresh(campaign)
    return campaign


@router.post("/{campaign_id}/cancel", response_model=CampaignOut)
def cancel_campaign(campaign_id: int, db: Session = Depends(get_db)):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if campaign.status in ("completed", "cancelled"):
        raise HTTPException(status_code=409, detail=f"Campaign already {campaign.status}")

    orchestrator.cancel_campaign(db, campaign)
    db.commit()
    db.refresh(campaign)
    return campaign


@router.get("/{campaign_id}/tasks", response_model=List[CampaignTaskOut])
def list_campaign_tasks(campaign_id: int, db: Session = Depends(get_db)):
    return (
        db.query(CampaignTask)
        .filter(CampaignTask.campaign_id == campaign_id)
        .order_by(CampaignTask.day, CampaignTask.id)
        .all()
    )


@router.post("/{campaign_id}/plan")
def generate_plan(campaign_id: int, db: Session = Depends(get_db)):
    """Use the planner agent to auto-generate tasks for a draft campaign."""
    from backend.services import agents

    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    persona = db.query(Persona).filter(Persona.id == campaign.persona_id).first()

    try:
        plan = agents.run_planner(
            db,
            {
                "campaign_id": campaign.id,
                "persona_id": campaign.persona_id,
                "total_days": campaign.total_days,
                "slots_per_day": (campaign.config or {}).get("slots_per_day", 3),
                "notes": campaign.description or "Standard campaign",
            },
            persona=persona,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Planner agent failed: {e}")

    # Convert plan into CampaignTask rows
    tasks_created = 0
    for day_plan in plan.get("days", []):
        day_num = day_plan.get("day", 1)
        for task_spec in day_plan.get("tasks", []):
            orchestrator.add_task(
                db,
                campaign,
                day=day_num,
                task_type=task_spec.get("type", "image"),
                config={
                    "prompt": task_spec.get("prompt", ""),
                    "platform": task_spec.get("platform"),
                    "notes": task_spec.get("notes"),
                },
            )
            tasks_created += 1

    db.commit()
    return {"tasks_created": tasks_created, "plan": plan}
