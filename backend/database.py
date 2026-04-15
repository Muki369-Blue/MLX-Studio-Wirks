from pathlib import Path
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, ForeignKey, Float, Boolean, JSON
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from datetime import datetime, timezone

DATABASE_PATH = Path(__file__).resolve().parent / "empire.db"
SQLALCHEMY_DATABASE_URL = f"sqlite:///{DATABASE_PATH}"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Persona(Base):
    __tablename__ = "personas"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    prompt_base = Column(Text, nullable=False)
    lora_name = Column(String, nullable=True)
    lora_status = Column(String, default="none")  # none | training | ready | failed
    personality = Column(Text, nullable=True)  # Chat personality description
    reference_image = Column(String, nullable=True)  # Path to face reference image for Redux
    voice = Column(String, nullable=True)  # Edge-TTS voice name (e.g. en-US-AriaNeural)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    contents = relationship("Content", back_populates="persona")
    schedules = relationship("Schedule", back_populates="persona")
    chat_messages = relationship("ChatMessage", back_populates="persona")
    analytics = relationship("Analytics", back_populates="persona")


class Content(Base):
    __tablename__ = "contents"

    id = Column(Integer, primary_key=True, index=True)
    persona_id = Column(Integer, ForeignKey("personas.id"), nullable=False)
    file_path = Column(String, nullable=True)
    prompt_used = Column(Text, nullable=True)
    comfy_job_id = Column(String, nullable=True)
    status = Column(String, default="pending")  # pending | generating | completed | upscaling | failed
    upscaled_path = Column(String, nullable=True)
    watermarked_path = Column(String, nullable=True)
    caption = Column(Text, nullable=True)
    hashtags = Column(Text, nullable=True)
    is_posted = Column(Boolean, default=False)
    posted_platforms = Column(Text, nullable=True)  # comma-separated
    set_id = Column(Integer, ForeignKey("content_sets.id"), nullable=True)
    set_order = Column(Integer, nullable=True)
    is_favorite = Column(Boolean, default=False)
    tags = Column(Text, nullable=True)  # comma-separated tags
    seed = Column(Integer, nullable=True)
    width = Column(Integer, default=1024)
    height = Column(Integer, default=1024)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    persona = relationship("Persona", back_populates="contents")
    content_set = relationship("ContentSet", back_populates="items")


class ContentSet(Base):
    """A set/album of related images."""
    __tablename__ = "content_sets"

    id = Column(Integer, primary_key=True, index=True)
    persona_id = Column(Integer, ForeignKey("personas.id"), nullable=False)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    scene_prompt = Column(Text, nullable=True)
    set_size = Column(Integer, default=5)
    status = Column(String, default="pending")  # pending | generating | completed | failed
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    items = relationship("Content", back_populates="content_set", order_by="Content.set_order")


class Schedule(Base):
    """Scheduled auto-generation rule."""
    __tablename__ = "schedules"

    id = Column(Integer, primary_key=True, index=True)
    persona_id = Column(Integer, ForeignKey("personas.id"), nullable=False)
    prompt_template = Column(Text, nullable=False)
    cron_expression = Column(String, nullable=False)  # e.g. "0 9,13,18 * * *"
    batch_size = Column(Integer, default=1)
    enabled = Column(Boolean, default=True)
    last_run = Column(DateTime, nullable=True)
    next_run = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    persona = relationship("Persona", back_populates="schedules")


class PostQueue(Base):
    """Posts queued for auto-publishing."""
    __tablename__ = "post_queue"

    id = Column(Integer, primary_key=True, index=True)
    content_id = Column(Integer, ForeignKey("contents.id"), nullable=False)
    platform = Column(String, nullable=False)  # onlyfans | fansly | twitter | reddit
    caption = Column(Text, nullable=True)
    scheduled_at = Column(DateTime, nullable=True)
    status = Column(String, default="pending")  # pending | posted | failed
    posted_at = Column(DateTime, nullable=True)
    error_detail = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    content = relationship("Content")


class ChatMessage(Base):
    """Fan chat / DM messages."""
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    persona_id = Column(Integer, ForeignKey("personas.id"), nullable=False)
    conversation_id = Column(String, nullable=False)  # group messages by fan
    role = Column(String, nullable=False)  # fan | persona
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    persona = relationship("Persona", back_populates="chat_messages")


class Analytics(Base):
    """Revenue & engagement tracking per persona."""
    __tablename__ = "analytics"

    id = Column(Integer, primary_key=True, index=True)
    persona_id = Column(Integer, ForeignKey("personas.id"), nullable=False)
    date = Column(DateTime, nullable=False)
    platform = Column(String, nullable=False)
    subscribers = Column(Integer, default=0)
    revenue = Column(Float, default=0.0)
    tips = Column(Float, default=0.0)
    messages_count = Column(Integer, default=0)
    likes = Column(Integer, default=0)
    views = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    persona = relationship("Persona", back_populates="analytics")


class Link(Base):
    __tablename__ = "links"

    id = Column(Integer, primary_key=True, index=True)
    platform = Column(String, nullable=False)
    url = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


def init_db():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
