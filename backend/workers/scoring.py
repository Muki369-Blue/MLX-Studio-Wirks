"""Scoring worker — evaluates generated content quality.

Uses a weighted model with configurable weights per dimension.
Scores are persisted to the asset_scores table.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from backend.database import AssetScore, Content, AgentRun
from backend.services import llm as llm_service

logger = logging.getLogger(__name__)

DEFAULT_WEIGHTS = {
    "aesthetic": 0.25,
    "persona_consistency": 0.25,
    "prompt_adherence": 0.20,
    "artifact_penalty": 0.15,
    "novelty": 0.15,
}

SCORING_SYSTEM = (
    "You are a quality assurance expert for AI-generated content. "
    "Score the described image on these dimensions (0.0 to 1.0):\n"
    "- aesthetic: visual appeal, composition, lighting\n"
    "- persona_consistency: does the image match the persona description?\n"
    "- prompt_adherence: does the image match what was requested?\n"
    "- artifact_penalty: 1.0 = no artifacts, 0.0 = severe artifacts\n"
    "- novelty: uniqueness compared to typical outputs\n\n"
    "Output ONLY valid JSON: {\"aesthetic\": 0.8, \"persona_consistency\": 0.9, "
    "\"prompt_adherence\": 0.85, \"artifact_penalty\": 0.95, \"novelty\": 0.7, \"notes\": \"brief note\"}"
)


def score_content(
    db: Session,
    content: Content,
    *,
    persona_description: str | None = None,
    weights: dict[str, float] | None = None,
) -> AssetScore:
    """Score a piece of content and persist the result."""
    import json as json_mod

    w = weights or DEFAULT_WEIGHTS
    start = time.time()

    # Create agent run audit entry
    agent_run = AgentRun(
        agent_type="scorer",
        persona_id=content.persona_id,
        input_payload={
            "content_id": content.id,
            "prompt_used": content.prompt_used,
            "persona_description": persona_description,
        },
        model_used=llm_service.OLLAMA_MODEL,
        status="running",
    )
    db.add(agent_run)
    db.flush()

    user_prompt = (
        f"Persona description: {persona_description or 'Not provided'}\n"
        f"Requested prompt: {content.prompt_used or 'Not provided'}\n"
        f"File: {content.file_path or 'Not available'}\n"
        "Score this generation."
    )

    try:
        raw = llm_service.generic_agent_call(
            SCORING_SYSTEM,
            user_prompt,
            temperature=0.3,
            num_predict=300,
            format="json",
        )
        scores = json_mod.loads(raw)
        duration = time.time() - start

        overall = sum(
            scores.get(dim, 0.5) * weight
            for dim, weight in w.items()
        )

        # Verdict thresholds
        if overall >= 0.75:
            verdict = "auto_approve"
        elif overall >= 0.5:
            verdict = "needs_review"
        else:
            verdict = "auto_reject"

        asset_score = AssetScore(
            content_id=content.id,
            aesthetic=scores.get("aesthetic"),
            persona_consistency=scores.get("persona_consistency"),
            prompt_adherence=scores.get("prompt_adherence"),
            artifact_penalty=scores.get("artifact_penalty"),
            novelty=scores.get("novelty"),
            overall=round(overall, 3),
            verdict=verdict,
            notes=scores.get("notes", ""),
            model_used=llm_service.OLLAMA_MODEL,
        )
        db.add(asset_score)

        agent_run.output_payload = {
            "scores": scores,
            "overall": overall,
            "verdict": verdict,
        }
        agent_run.status = "completed"
        agent_run.duration_seconds = duration
        agent_run.finished_at = datetime.now(timezone.utc)
        db.flush()

        return asset_score

    except Exception as e:
        logger.error("Scoring failed for content %d: %s", content.id, e)
        agent_run.status = "failed"
        agent_run.error = str(e)
        agent_run.finished_at = datetime.now(timezone.utc)
        db.flush()

        # Return a default needs_review score
        asset_score = AssetScore(
            content_id=content.id,
            overall=0.5,
            verdict="needs_review",
            notes=f"Scoring failed: {e}",
            model_used=llm_service.OLLAMA_MODEL,
        )
        db.add(asset_score)
        db.flush()
        return asset_score
