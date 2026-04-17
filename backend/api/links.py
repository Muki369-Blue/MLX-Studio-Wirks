"""Links API — CRUD for platform links."""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

try:
    from ..database import get_db, Link
    from ..schemas import LinkCreate, LinkOut
except ImportError:
    from database import get_db, Link
    from schemas import LinkCreate, LinkOut

router = APIRouter(tags=["links"])


@router.post("/links/", response_model=LinkOut)
def create_link(body: LinkCreate, db: Session = Depends(get_db)):
    link = Link(platform=body.platform, url=body.url)
    db.add(link)
    db.commit()
    db.refresh(link)
    return link


@router.get("/links/", response_model=List[LinkOut])
def list_links(db: Session = Depends(get_db)):
    return db.query(Link).order_by(Link.id.desc()).all()


@router.delete("/links/{link_id}")
def delete_link(link_id: int, db: Session = Depends(get_db)):
    link = db.query(Link).filter(Link.id == link_id).first()
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")
    db.delete(link)
    db.commit()
    return {"status": "deleted"}
