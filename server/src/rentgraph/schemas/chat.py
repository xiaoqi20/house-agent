"""上下文问答（PRD §5 流程 C）：回答必须带引用，找不到依据要降级。"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

AnswerMode = Literal["context", "house_only", "general", "refusal", "out_of_scope"]


class CitationOut(BaseModel):
    clause_id: str | None = None
    clause_no: int | None = None
    label: str = ""
    contract_id: str | None = None
    page: int | None = None
    char_start: int | None = None
    char_end: int | None = None


class ConversationCreate(BaseModel):
    workspace_id: str
    title: str = "新对话"


class ConversationOut(BaseModel):
    id: str
    workspace_id: str
    title: str
    created_at: datetime | None = None
    message_count: int = 0


class MessageCreate(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    house_id: str | None = None
    contract_id: str | None = None


class MessageOut(BaseModel):
    id: str
    role: Literal["user", "ai"] = "user"
    content: dict[str, Any] = Field(default_factory=dict)
    citations: list[CitationOut] = Field(default_factory=list)
    created_at: datetime | None = None


class MessageCreated(BaseModel):
    message_id: str
    run_id: str


class AnswerOut(BaseModel):
    message_id: str
    mode: AnswerMode = "general"
    html: str = ""
    citations: list[CitationOut] = Field(default_factory=list)
    followups: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
