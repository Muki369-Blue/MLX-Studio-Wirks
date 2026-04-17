"""Agents API — invoke planner, creative, analyst; view agent runs."""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database import get_db, AgentRun, Persona
from backend.schemas import AgentRunOut
from backend.services import agents

router = APIRouter(prefix="/agents", tags=["agents"])


class PlannerRequest(BaseModel):
    persona_id: int
    total_days: int = 4
    slots_per_day: int = 3
    notes: Optional[str] = None


class CreativeRequest(BaseModel):
    persona_id: Optional[int] = None
    brief: str
    content_type: str = "image"


class AnalystRequest(BaseModel):
    persona_id: Optional[int] = None
    metrics_summary: dict


@router.post("/planner")
def invoke_planner(body: PlannerRequest, db: Session = Depends(get_db)):
    persona = db.query(Persona).filter(Persona.id == body.persona_id).first()
    if not persona:
        raise HTTPException(status_code=404, detail="Persona not found")
    try:
        plan = agents.run_planner(
            db,
            {
                "persona_id": body.persona_id,
                "total_days": body.total_days,
                "slots_per_day": body.slots_per_day,
                "notes": body.notes,
            },
            persona=persona,
        )
        db.commit()
        return plan
    except Exception as e:
        db.commit()  # commit the failed agent_run record
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/creative")
def invoke_creative(body: CreativeRequest, db: Session = Depends(get_db)):
    persona = None
    if body.persona_id:
        persona = db.query(Persona).filter(Persona.id == body.persona_id).first()
    try:
        spec = agents.run_creative(db, persona=persona, brief=body.brief, content_type=body.content_type)
        db.commit()
        return spec
    except Exception as e:
        db.commit()
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/analyst")
def invoke_analyst(body: AnalystRequest, db: Session = Depends(get_db)):
    persona = None
    if body.persona_id:
        persona = db.query(Persona).filter(Persona.id == body.persona_id).first()
    try:
        analysis = agents.run_analyst(db, persona=persona, metrics_summary=body.metrics_summary)
        db.commit()
        return analysis
    except Exception as e:
        db.commit()
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/runs", response_model=List[AgentRunOut])
def list_agent_runs(
    agent_type: Optional[str] = None,
    persona_id: Optional[int] = None,
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
):
    q = db.query(AgentRun)
    if agent_type:
        q = q.filter(AgentRun.agent_type == agent_type)
    if persona_id:
        q = q.filter(AgentRun.persona_id == persona_id)
    return q.order_by(AgentRun.id.desc()).limit(limit).all()
