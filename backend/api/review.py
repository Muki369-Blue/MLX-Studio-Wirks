"""Review Inbox API — score, approve/reject/rerun content."""
from __future__ import annotations

import threading
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.database import (
    get_db,
    AssetScore,
    Content,
    Persona,
    GenerationJob,
    JobState,
    PersonaMemory,
)
from backend.schemas import AssetScoreOut, AssetReviewAction
from backend.services import jobs as jobs_service

router = APIRouter(prefix="/review", tags=["review"])


@router.get("/inbox")
def review_inbox(
    verdict: Optional[str] = None,
    persona_id: Optional[int] = None,
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
):
    """List content that needs review, optionally filtered by verdict or persona."""
    q = (
        db.query(Content, AssetScore)
        .outerjoin(AssetScore, AssetScore.content_id == Content.id)
        .filter(Content.status == "completed")
    )

    if verdict:
        q = q.filter(AssetScore.verdict == verdict)
    else:
        # Default: show needs_review items, plus unscored
        q = q.filter(
            (AssetScore.verdict == "needs_review") | (AssetScore.id == None)
        )

    if persona_id:
        q = q.filter(Content.persona_id == persona_id)

    rows = q.order_by(Content.id.desc()).limit(limit).all()

    return [
        {
            "content": {
                "id": c.id,
                "persona_id": c.persona_id,
                "file_path": c.file_path,
                "upscaled_path": c.upscaled_path,
                "prompt_used": c.prompt_used,
                "tags": c.tags,
                "created_at": c.created_at,
            },
            "score": {
                "id": s.id,
                "aesthetic": s.aesthetic,
                "persona_consistency": s.persona_consistency,
                "prompt_adherence": s.prompt_adherence,
                "artifact_penalty": s.artifact_penalty,
                "novelty": s.novelty,
                "overall": s.overall,
                "verdict": s.verdict,
                "notes": s.notes,
            } if s else None,
        }
        for c, s in rows
    ]


@router.post("/{content_id}/score", response_model=AssetScoreOut)
def score_content(content_id: int, db: Session = Depends(get_db)):
    """Trigger scoring for a specific content item."""
    from backend.workers.scoring import score_content as do_score

    content = db.query(Content).filter(Content.id == content_id).first()
    if not content:
        raise HTTPException(status_code=404, detail="Content not found")

    persona = db.query(Persona).filter(Persona.id == content.persona_id).first() if content.persona_id else None
    score = do_score(db, content, persona_description=persona.prompt_base if persona else None)
    db.commit()
    return score


@router.post("/{content_id}/action")
def review_action(content_id: int, body: AssetReviewAction, db: Session = Depends(get_db)):
    """Approve, reject, or rerun a content item."""
    content = db.query(Content).filter(Content.id == content_id).first()
    if not content:
        raise HTTPException(status_code=404, detail="Content not found")

    gjob = jobs_service.job_for_content(db, content_id)

    if body.action == "approve":
        if gjob:
            jobs_service.transition(db, gjob, JobState.APPROVED, actor="user", note=body.notes)
        # Update score verdict
        score = db.query(AssetScore).filter(AssetScore.content_id == content_id).order_by(AssetScore.id.desc()).first()
        if score:
            score.verdict = "auto_approve"
            score.notes = body.notes or score.notes
        # Save learned memory if notes provided
        if body.notes and content.persona_id:
            _save_review_note(db, content.persona_id, body.notes, approved=True)
        db.commit()
        return {"status": "approved"}

    elif body.action == "reject":
        if gjob:
            jobs_service.transition(db, gjob, JobState.FAILED, actor="user", note=body.notes)
        score = db.query(AssetScore).filter(AssetScore.content_id == content_id).order_by(AssetScore.id.desc()).first()
        if score:
            score.verdict = "auto_reject"
            score.notes = body.notes or score.notes
        if body.notes and content.persona_id:
            _save_review_note(db, content.persona_id, body.notes, approved=False)
        db.commit()
        return {"status": "rejected"}

    elif body.action == "rerun":
        # Reset content status and create a new job
        content.status = "pending"
        content.file_path = None
        content.upscaled_path = None
        content.watermarked_path = None
        new_job = jobs_service.create_job(
            db,
            job_type=gjob.job_type if gjob else "image",
            persona_id=content.persona_id,
            content_id=content.id,
            payload=gjob.payload if gjob else {"prompt": content.prompt_used},
            actor="user",
        )
        db.commit()
        return {"status": "rerun_queued", "new_job_id": new_job.id}

    raise HTTPException(status_code=400, detail="Invalid action. Use: approve, reject, rerun")


def _save_review_note(db: Session, persona_id: int, notes: str, approved: bool):
    """Append review feedback to persona learned memory."""
    from datetime import datetime, timezone

    key = "review_feedback"
    existing = (
        db.query(PersonaMemory)
        .filter(
            PersonaMemory.persona_id == persona_id,
            PersonaMemory.partition == "learned",
            PersonaMemory.key == key,
        )
        .first()
    )
    entry = {
        "note": notes,
        "approved": approved,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if existing:
        feedback_list = existing.value.get("feedback", [])
        feedback_list.append(entry)
        # Keep last 50 entries
        existing.value = {"feedback": feedback_list[-50:]}
        existing.updated_at = datetime.now(timezone.utc)
    else:
        db.add(PersonaMemory(
            persona_id=persona_id,
            partition="learned",
            key=key,
            value={"feedback": [entry]},
            source="user:review",
        ))
    db.flush()
