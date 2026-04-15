from datetime import datetime
from pydantic import BaseModel
from typing import Optional, List


class PersonaCreate(BaseModel):
    name: str
    prompt_base: str
    lora_name: Optional[str] = None
    personality: Optional[str] = None
    voice: Optional[str] = None


class PersonaOut(BaseModel):
    id: int
    name: str
    prompt_base: str
    lora_name: Optional[str]
    lora_status: Optional[str] = "none"
    personality: Optional[str] = None
    reference_image: Optional[str] = None
    voice: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class GenerationRequest(BaseModel):
    prompt_extra: str
    batch_size: int = 1
    negative_prompt: Optional[str] = None
    lora_override: Optional[str] = None


class GenerationOut(BaseModel):
    id: int
    persona_id: int
    file_path: Optional[str]
    prompt_used: Optional[str]
    comfy_job_id: Optional[str]
    status: str
    upscaled_path: Optional[str] = None
    watermarked_path: Optional[str] = None
    caption: Optional[str] = None
    hashtags: Optional[str] = None
    is_posted: bool = False
    posted_platforms: Optional[str] = None
    set_id: Optional[int] = None
    set_order: Optional[int] = None
    is_favorite: bool = False
    tags: Optional[str] = None
    seed: Optional[int] = None
    width: int = 1024
    height: int = 1024
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ─── Content Sets ────────────────────────────────────────────────────

class ContentSetCreate(BaseModel):
    persona_id: int
    name: str
    description: Optional[str] = None
    scene_prompt: str
    set_size: int = 5
    negative_prompt: Optional[str] = None
    lora_override: Optional[str] = None


class ContentSetOut(BaseModel):
    id: int
    persona_id: int
    name: str
    description: Optional[str]
    scene_prompt: Optional[str]
    set_size: int
    status: str
    created_at: Optional[datetime] = None
    items: List[GenerationOut] = []

    class Config:
        from_attributes = True


# ─── Schedules ───────────────────────────────────────────────────────

class ScheduleCreate(BaseModel):
    persona_id: int
    prompt_template: str
    cron_expression: str  # e.g. "0 9,13,18 * * *"
    batch_size: int = 1


class ScheduleOut(BaseModel):
    id: int
    persona_id: int
    prompt_template: str
    cron_expression: str
    batch_size: int
    enabled: bool
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ─── Post Queue ──────────────────────────────────────────────────────

class PostQueueCreate(BaseModel):
    content_id: int
    platform: str
    caption: Optional[str] = None
    scheduled_at: Optional[datetime] = None


class PostQueueOut(BaseModel):
    id: int
    content_id: int
    platform: str
    caption: Optional[str]
    scheduled_at: Optional[datetime]
    status: str
    posted_at: Optional[datetime] = None
    error_detail: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ─── Chat ────────────────────────────────────────────────────────────

class ChatMessageIn(BaseModel):
    message: str


class ChatMessageOut(BaseModel):
    id: int
    persona_id: int
    conversation_id: str
    role: str
    message: str
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ─── Analytics ───────────────────────────────────────────────────────

class AnalyticsEntry(BaseModel):
    persona_id: int
    date: datetime
    platform: str
    subscribers: int = 0
    revenue: float = 0.0
    tips: float = 0.0
    messages_count: int = 0
    likes: int = 0
    views: int = 0


class AnalyticsOut(BaseModel):
    id: int
    persona_id: int
    date: datetime
    platform: str
    subscribers: int
    revenue: float
    tips: float
    messages_count: int
    likes: int
    views: int
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class AnalyticsSummary(BaseModel):
    total_revenue: float
    total_tips: float
    total_subscribers: int
    total_content: int
    top_persona: Optional[str] = None
    by_platform: dict = {}
    by_persona: List[dict] = []


# ─── Links ───────────────────────────────────────────────────────────

class LinkCreate(BaseModel):
    platform: str
    url: str


class LinkOut(BaseModel):
    id: int
    platform: str
    url: str

    class Config:
        from_attributes = True


# ─── LoRA Training ───────────────────────────────────────────────────

class LoraTrainingRequest(BaseModel):
    persona_id: int
    training_steps: int = 1000
    learning_rate: float = 1e-4


# ─── Caption / Hashtag ───────────────────────────────────────────────

class CaptionRequest(BaseModel):
    content_id: int
    platform: str = "onlyfans"  # onlyfans | twitter | reddit | fansly


class CaptionOut(BaseModel):
    caption: str
    hashtags: str

    class Config:
        from_attributes = True
