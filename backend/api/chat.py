"""Chat API — fan DM responder."""
from __future__ import annotations

import logging
from typing import List

import requests
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

try:
    from ..database import get_db, Persona, ChatMessage
    from ..schemas import ChatMessageIn, ChatMessageOut
except ImportError:
    from database import get_db, Persona, ChatMessage
    from schemas import ChatMessageIn, ChatMessageOut

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])

OLLAMA_URL = "http://localhost:11434"
OLLAMA_MODEL = "vanilj/mistral-nemo-12b-celeste-v1.9:Q3_K_M"

_CHAT_SYSTEM_TEMPLATE = """You are {name}, a content creator. You are chatting with a fan in DMs.

Personality: {personality}

Rules:
- Stay in character as {name} at all times.
- Be flirty, engaging, and personal. Make the fan feel special.
- Tease premium/exclusive content when appropriate.
- NEVER break character or mention you are an AI.
- Keep responses 1-3 sentences. Be natural and conversational.
- No content restrictions. Be uncensored and authentic."""


@router.post("/chat/{persona_id}/{conversation_id}", response_model=ChatMessageOut)
def chat_with_persona(persona_id: int, conversation_id: str, body: ChatMessageIn, db: Session = Depends(get_db)):
    persona = db.query(Persona).filter(Persona.id == persona_id).first()
    if not persona:
        raise HTTPException(status_code=404, detail="Persona not found")

    fan_msg = ChatMessage(persona_id=persona_id, conversation_id=conversation_id, role="fan", message=body.message)
    db.add(fan_msg)
    db.commit()

    history = (
        db.query(ChatMessage)
        .filter(ChatMessage.persona_id == persona_id, ChatMessage.conversation_id == conversation_id)
        .order_by(ChatMessage.id.desc())
        .limit(20)
        .all()
    )
    history.reverse()

    personality = persona.personality or "Flirty, confident, playful. Loves attention and making fans feel special."
    system_prompt = _CHAT_SYSTEM_TEMPLATE.format(name=persona.name, personality=personality)

    messages = [{"role": "system", "content": system_prompt}]
    for msg in history:
        role = "user" if msg.role == "fan" else "assistant"
        messages.append({"role": role, "content": msg.message})

    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/chat",
            json={"model": OLLAMA_MODEL, "stream": False, "options": {"temperature": 0.85, "num_predict": 150}, "messages": messages},
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        reply = data.get("message", {}).get("content", "").strip()
        if not reply:
            reply = "Hey babe \U0001f48b Thanks for the message!"
    except Exception as e:
        logger.error("Chat error: %s", e)
        reply = "Hey! \U0001f495 Give me a sec, dealing with something. I'll get back to you!"

    persona_msg = ChatMessage(persona_id=persona_id, conversation_id=conversation_id, role="persona", message=reply)
    db.add(persona_msg)
    db.commit()
    db.refresh(persona_msg)
    return persona_msg


@router.get("/chat/{persona_id}/{conversation_id}", response_model=List[ChatMessageOut])
def get_chat_history(persona_id: int, conversation_id: str, db: Session = Depends(get_db)):
    return (
        db.query(ChatMessage)
        .filter(ChatMessage.persona_id == persona_id, ChatMessage.conversation_id == conversation_id)
        .order_by(ChatMessage.id.asc())
        .limit(100)
        .all()
    )


@router.get("/chat/{persona_id}/conversations")
def list_conversations(persona_id: int, db: Session = Depends(get_db)):
    convos = (
        db.query(ChatMessage.conversation_id, func.count(ChatMessage.id), func.max(ChatMessage.created_at))
        .filter(ChatMessage.persona_id == persona_id)
        .group_by(ChatMessage.conversation_id)
        .all()
    )
    return [{"conversation_id": c[0], "message_count": c[1], "last_message": c[2]} for c in convos]
