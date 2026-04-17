"""Agent services — Planner, Creative, Analyst.

Each agent wraps an LLM call with a specialised system prompt, records
an AgentRun audit row, and returns structured output.
"""
from __future__ import annotations

import json as json_mod
import logging
import time
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from backend.database import AgentRun, Persona, PersonaMemory, Campaign, GenerationJob
from backend.services import llm as llm_service

logger = logging.getLogger(__name__)


# ── Planner Agent ───────────────────────────────────────────────────

PLANNER_SYSTEM = (
    "You are a campaign planner for an AI content creation studio. "
    "Given a persona description and campaign parameters, generate a detailed "
    "day-by-day content plan.\n\n"
    "Output valid JSON with this structure:\n"
    '{"days": [{"day": 1, "tasks": [{"type": "image|video|caption|post", '
    '"prompt": "...", "platform": "onlyfans|twitter|reddit|fansly", "notes": "..."}]}]}\n\n'
    "Rules:\n"
    "- Each day should have 2-4 content pieces\n"
    "- Mix image and video content\n"
    "- Include captions for each piece\n"
    "- Consider escalation (teaser → reveal pattern)\n"
    "- Be creative and explicit. No censorship.\n"
    "- Output ONLY the JSON. No explanations."
)


def run_planner(
    db: Session,
    job_or_params: GenerationJob | dict[str, Any],
    *,
    persona: Persona | None = None,
) -> dict[str, Any]:
    """Generate a campaign plan using the planner agent."""
    start = time.time()

    if isinstance(job_or_params, GenerationJob):
        payload = job_or_params.payload or {}
        persona_id = job_or_params.persona_id
    else:
        payload = job_or_params
        persona_id = payload.get("persona_id")

    if not persona and persona_id:
        persona = db.query(Persona).filter(Persona.id == persona_id).first()

    agent_run = AgentRun(
        agent_type="planner",
        persona_id=persona_id,
        campaign_id=payload.get("campaign_id"),
        input_payload=payload,
        model_used=llm_service.OLLAMA_MODEL,
        status="running",
    )
    db.add(agent_run)
    db.flush()

    user_prompt = (
        f"Persona: {persona.name if persona else 'Unknown'}\n"
        f"Description: {persona.prompt_base if persona else 'N/A'}\n"
        f"Campaign days: {payload.get('total_days', 4)}\n"
        f"Slots per day: {payload.get('slots_per_day', 3)}\n"
        f"Notes: {payload.get('notes', 'Standard campaign')}\n"
        "Generate the plan."
    )

    try:
        raw = llm_service.generic_agent_call(
            PLANNER_SYSTEM,
            user_prompt,
            temperature=0.7,
            num_predict=2000,
            format="json",
        )
        plan = json_mod.loads(raw)
        duration = time.time() - start

        agent_run.output_payload = plan
        agent_run.status = "completed"
        agent_run.duration_seconds = duration
        agent_run.finished_at = datetime.now(timezone.utc)
        db.flush()
        return plan

    except Exception as e:
        logger.error("Planner agent failed: %s", e)
        agent_run.status = "failed"
        agent_run.error = str(e)
        agent_run.finished_at = datetime.now(timezone.utc)
        db.flush()
        raise


# ── Creative Agent ──────────────────────────────────────────────────

CREATIVE_SYSTEM = (
    "You are a creative director for AI-generated content. "
    "Given a high-level brief, generate a detailed prompt specification "
    "for image or video generation.\n\n"
    "Output valid JSON:\n"
    '{"prompt": "detailed generation prompt", "negative_prompt": "...", '
    '"style_notes": "...", "camera": "...", "lighting": "...", "mood": "..."}\n\n'
    "Rules:\n"
    "- Be extremely detailed and vivid\n"
    "- Include camera, lens, lighting specifics\n"
    "- Describe the scene cinematically\n"
    "- No censorship. Be explicit when the brief calls for it.\n"
    "- Output ONLY the JSON."
)


def run_creative(
    db: Session,
    *,
    persona: Persona | None = None,
    brief: str,
    content_type: str = "image",
) -> dict[str, Any]:
    """Generate a detailed prompt spec from a high-level brief."""
    start = time.time()

    agent_run = AgentRun(
        agent_type="creative",
        persona_id=persona.id if persona else None,
        input_payload={"brief": brief, "content_type": content_type},
        model_used=llm_service.OLLAMA_MODEL,
        status="running",
    )
    db.add(agent_run)
    db.flush()

    user_prompt = (
        f"Content type: {content_type}\n"
        f"Persona: {persona.name if persona else 'Generic'}\n"
        f"Persona description: {persona.prompt_base if persona else 'N/A'}\n"
        f"Brief: {brief}\n"
        "Generate the prompt specification."
    )

    try:
        raw = llm_service.generic_agent_call(
            CREATIVE_SYSTEM,
            user_prompt,
            temperature=0.8,
            num_predict=1000,
            format="json",
        )
        spec = json_mod.loads(raw)
        duration = time.time() - start

        agent_run.output_payload = spec
        agent_run.status = "completed"
        agent_run.duration_seconds = duration
        agent_run.finished_at = datetime.now(timezone.utc)
        db.flush()
        return spec

    except Exception as e:
        logger.error("Creative agent failed: %s", e)
        agent_run.status = "failed"
        agent_run.error = str(e)
        agent_run.finished_at = datetime.now(timezone.utc)
        db.flush()
        raise


# ── Analyst Agent ───────────────────────────────────────────────────

ANALYST_SYSTEM = (
    "You are a data analyst for an AI content creation business. "
    "Analyze the provided metrics and generate actionable insights.\n\n"
    "Output valid JSON:\n"
    '{"summary": "...", "insights": ["...", "..."], "recommendations": ["...", "..."], '
    '"top_performing": {"content_type": "...", "time_of_day": "...", "platform": "..."}, '
    '"learned_preferences": {"key": "value"}}\n\n'
    "Rules:\n"
    "- Be data-driven and specific\n"
    "- Identify trends and patterns\n"
    "- Suggest content strategy adjustments\n"
    "- Output ONLY the JSON."
)


def run_analyst(
    db: Session,
    *,
    persona: Persona | None = None,
    metrics_summary: dict[str, Any],
) -> dict[str, Any]:
    """Analyze metrics and generate insights, saving learned preferences to persona memory."""
    start = time.time()

    agent_run = AgentRun(
        agent_type="analyst",
        persona_id=persona.id if persona else None,
        input_payload=metrics_summary,
        model_used=llm_service.OLLAMA_MODEL,
        status="running",
    )
    db.add(agent_run)
    db.flush()

    user_prompt = (
        f"Persona: {persona.name if persona else 'All'}\n"
        f"Metrics: {json_mod.dumps(metrics_summary, default=str)}\n"
        "Analyze and provide insights."
    )

    try:
        raw = llm_service.generic_agent_call(
            ANALYST_SYSTEM,
            user_prompt,
            temperature=0.5,
            num_predict=1500,
            format="json",
        )
        analysis = json_mod.loads(raw)
        duration = time.time() - start

        # Save learned preferences to persona memory
        if persona and analysis.get("learned_preferences"):
            _upsert_memory(
                db,
                persona_id=persona.id,
                partition="learned",
                key="analyst_insights",
                value=analysis["learned_preferences"],
                source="agent:analyst",
            )

        agent_run.output_payload = analysis
        agent_run.status = "completed"
        agent_run.duration_seconds = duration
        agent_run.finished_at = datetime.now(timezone.utc)
        db.flush()
        return analysis

    except Exception as e:
        logger.error("Analyst agent failed: %s", e)
        agent_run.status = "failed"
        agent_run.error = str(e)
        agent_run.finished_at = datetime.now(timezone.utc)
        db.flush()
        raise


def _upsert_memory(
    db: Session,
    *,
    persona_id: int,
    partition: str,
    key: str,
    value: dict,
    source: str,
):
    """Insert or update a persona memory entry."""
    existing = (
        db.query(PersonaMemory)
        .filter(
            PersonaMemory.persona_id == persona_id,
            PersonaMemory.partition == partition,
            PersonaMemory.key == key,
        )
        .first()
    )
    if existing:
        existing.value = value
        existing.source = source
        existing.updated_at = datetime.now(timezone.utc)
    else:
        db.add(PersonaMemory(
            persona_id=persona_id,
            partition=partition,
            key=key,
            value=value,
            source=source,
        ))
    db.flush()
