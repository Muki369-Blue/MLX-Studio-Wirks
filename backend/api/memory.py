"""Persona Memory API — CRUD for structured persona memory."""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.database import get_db, PersonaMemory, Persona
from backend.schemas import PersonaMemoryCreate, PersonaMemoryOut

router = APIRouter(prefix="/persona-memory", tags=["persona-memory"])


@router.get("/{persona_id}", response_model=List[PersonaMemoryOut])
def list_memories(
    persona_id: int,
    partition: Optional[str] = None,
    db: Session = Depends(get_db),
):
    q = db.query(PersonaMemory).filter(PersonaMemory.persona_id == persona_id)
    if partition:
        q = q.filter(PersonaMemory.partition == partition)
    return q.order_by(PersonaMemory.partition, PersonaMemory.key).all()


@router.post("/", response_model=PersonaMemoryOut)
def upsert_memory(body: PersonaMemoryCreate, db: Session = Depends(get_db)):
    persona = db.query(Persona).filter(Persona.id == body.persona_id).first()
    if not persona:
        raise HTTPException(status_code=404, detail="Persona not found")

    existing = (
        db.query(PersonaMemory)
        .filter(
            PersonaMemory.persona_id == body.persona_id,
            PersonaMemory.partition == body.partition,
            PersonaMemory.key == body.key,
        )
        .first()
    )
    if existing:
        existing.value = body.value
        existing.source = body.source
        db.commit()
        db.refresh(existing)
        return existing

    mem = PersonaMemory(
        persona_id=body.persona_id,
        partition=body.partition,
        key=body.key,
        value=body.value,
        source=body.source,
    )
    db.add(mem)
    db.commit()
    db.refresh(mem)
    return mem


@router.delete("/{memory_id}")
def delete_memory(memory_id: int, db: Session = Depends(get_db)):
    mem = db.query(PersonaMemory).filter(PersonaMemory.id == memory_id).first()
    if not mem:
        raise HTTPException(status_code=404, detail="Memory entry not found")
    db.delete(mem)
    db.commit()
    return {"status": "deleted"}
