from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class UserOut(BaseModel):
    id: int
    name: str
    username: str
    role: str
    team_id: int | None = None

    class Config:
        from_attributes = True


class LoginIn(BaseModel):
    username: str
    password: str


class LoginOut(BaseModel):
    token: str
    user: UserOut


class UserProfileUpdateIn(BaseModel):
    name: str | None = None
    password: str | None = None


class LLMConfigUpdateIn(BaseModel):
    api_key: str | None = None
    clear_api_key: bool = False
    base_url: str | None = None
    model_name: str | None = None
    model_id: str | None = None


class LLMConfigOut(BaseModel):
    provider: str
    base_url: str
    model_name: str
    model_id: str
    has_api_key: bool
    api_key_masked: str
    llm_configured: bool
    llm_mode: str


class LLMConnectionTestOut(BaseModel):
    ok: bool
    message: str
    model_id: str
    latency_ms: int


class KnowledgeIn(BaseModel):
    title: str
    source_type: str
    source_name: str
    stage: str
    scenario: str
    customer_type: str = "通用"
    recommended: str
    banned: str = ""
    content: str


class KnowledgeOut(KnowledgeIn):
    id: int
    chunk_type: str = "知识片段"
    section_title: str = ""
    page_start: int | None = None
    page_end: int | None = None
    confidence: int = 70
    chunk_metadata: Any = None
    display_order: int = 0
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class KnowledgeDocumentVersionOut(BaseModel):
    id: int
    document_id: int
    version_label: str
    file_name: str
    parse_status: str
    parse_summary: str = ""
    error_message: str = ""
    structured_data: Any = None
    chunk_count: int
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class KnowledgeDocumentOut(BaseModel):
    id: int
    title: str
    source_type: str
    source_name: str
    tags: str = ""
    purpose: str = ""
    stage: str
    scenario: str
    customer_type: str
    recommended: str
    banned: str
    parse_status: str = "parsed"
    parse_summary: str = ""
    error_message: str = ""
    status: str
    current_version_id: int | None
    created_at: datetime
    current_version: KnowledgeDocumentVersionOut | None = None
    versions: list[KnowledgeDocumentVersionOut] = []

    class Config:
        from_attributes = True


class KnowledgeDocumentUpdateIn(BaseModel):
    title: str
    source_type: str
    tags: str = ""
    reparse: bool = False


class KnowledgeChunkPageOut(BaseModel):
    items: list[KnowledgeOut]
    total: int
    page: int
    page_size: int


class TrainingStartIn(BaseModel):
    training_type: str
    stage: str
    goal: str
    customer_name: str
    customer_type: str
    customer_difficulty: str = "标准"
    customer_personality: str = "谨慎型"
    customer_concern: str = "价格"
    template_id: str = ""
    setup_context: dict[str, Any] = Field(default_factory=dict)
    background: str


class MessageIn(BaseModel):
    content: str
    speaker: str | None = None


class MessageOut(BaseModel):
    id: int
    role: str
    content: str
    speaker: str = "buyer"

    class Config:
        from_attributes = True


class VoiceTranscribeIn(BaseModel):
    audio_base64: str
    mime_type: str = "audio/wav"


class VoiceSpeechIn(BaseModel):
    text: str
    speaker: str = "buyer"


class SuggestionOut(BaseModel):
    content: str
    notice: str = "AI 推荐回复仅用于训练参考，并不完全适用于实际业务场景。"


class TrainingSessionOut(BaseModel):
    id: int
    training_type: str
    stage: str
    goal: str
    customer_name: str
    customer_type: str
    customer_difficulty: str = "标准"
    customer_personality: str = "谨慎型"
    customer_concern: str = "价格"
    template_id: str = ""
    setup_context: dict[str, Any] | None = Field(default_factory=dict)
    background: str
    status: str
    created_at: datetime
    messages: list[MessageOut] = []

    class Config:
        from_attributes = True


class ReportOut(BaseModel):
    id: int
    session_id: int
    overall_score: int
    summary: str
    scores: Any
    good_lines: Any
    risk_lines: Any
    alternatives: Any
    checklist: Any
    citations: Any
    created_at: datetime

    class Config:
        from_attributes = True
