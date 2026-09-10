"""RentGraph 一期 ORM（对应 doc/plan/后端-v1.1-接口契约.md §3）。

一期数据边界：所有业务数据挂在 `workspaces`（临时工作台）下，`expires_at` 到期即不可用。
JSON 字段在 SQLite 与 Postgres 上通用（Postgres 下用 JSONB）。
"""

import enum
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

JSONType = JSON().with_variant(JSONB, "postgresql")


def uid() -> str:
    return uuid.uuid4().hex


def utcnow() -> datetime:
    return datetime.now(UTC)


class ContractStatus(enum.StrEnum):
    uploaded = "uploaded"
    parsing = "parsing"
    analyzing = "analyzing"
    done = "done"
    failed = "failed"


class RiskLevel(enum.StrEnum):
    high = "high"
    medium = "medium"
    low = "low"


class RunStatus(enum.StrEnum):
    queued = "queued"
    running = "running"
    interrupted = "interrupted"
    done = "done"
    failed = "failed"
    cancelled = "cancelled"


# ==================== 工作台 ====================


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    title: Mapped[str] = mapped_column(String(64), default="本次工作台")
    ctx_house_id: Mapped[str | None] = mapped_column(String(32))
    ctx_contract_id: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: utcnow() + timedelta(hours=72)
    )

    houses: Mapped[list["House"]] = relationship(back_populates="workspace", cascade="all, delete-orphan")
    contracts: Mapped[list["Contract"]] = relationship(back_populates="workspace", cascade="all, delete-orphan")


# ==================== 房源导入与候选房源 ====================


class ImportBatch(Base):
    __tablename__ = "import_batches"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    source: Mapped[str] = mapped_column(String(16), default="paste")  # paste|manual|batch|file|link
    filename: Mapped[str | None] = mapped_column(String(255))
    storage_key: Mapped[str | None] = mapped_column(String(512))
    raw_text: Mapped[str | None] = mapped_column(Text)
    link_url: Mapped[str | None] = mapped_column(Text)
    # parsing|extracting|ready|confirmed|failed|cancelled
    status: Mapped[str] = mapped_column(String(16), default="parsing")
    drafts: Mapped[list | None] = mapped_column(JSONType)  # 未经确认的字段（不得进入推荐）
    house_count: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[dict | None] = mapped_column(JSONType)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class House(Base):
    __tablename__ = "houses"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    batch_id: Mapped[str | None] = mapped_column(String(32))
    no: Mapped[str] = mapped_column(String(16), default="H1")
    status: Mapped[str] = mapped_column(String(16), default="active")  # active|dropped
    drop_reason: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(16), default="paste")
    raw: Mapped[str] = mapped_column(Text, default="")
    link_url: Mapped[str] = mapped_column(Text, default="")

    name: Mapped[str] = mapped_column(Text, default="")
    region: Mapped[str] = mapped_column(Text, default="")
    address: Mapped[str] = mapped_column(Text, default="")
    rent: Mapped[int | None] = mapped_column(Integer)
    deposit: Mapped[str | None] = mapped_column(Text)
    agency_fee: Mapped[int | None] = mapped_column(Integer)
    property_fee: Mapped[int | None] = mapped_column(Integer)
    property_bear: Mapped[str] = mapped_column(Text, default="")
    net_fee: Mapped[int | None] = mapped_column(Integer)
    other_fee: Mapped[str | None] = mapped_column(Text)
    area: Mapped[float | None] = mapped_column(Float)
    layout: Mapped[str] = mapped_column(Text, default="")
    floor: Mapped[str] = mapped_column(Text, default="")
    orientation: Mapped[str] = mapped_column(Text, default="")
    bathroom: Mapped[bool | None] = mapped_column(Boolean)
    lighting: Mapped[str] = mapped_column(Text, default="")
    furniture: Mapped[str] = mapped_column(Text, default="")
    commute_min: Mapped[int | None] = mapped_column(Integer)
    commute_mode: Mapped[str] = mapped_column(Text, default="地铁")
    metro: Mapped[str] = mapped_column(Text, default="")
    nearby: Mapped[str] = mapped_column(Text, default="")
    pet: Mapped[str] = mapped_column(Text, default="")
    shared: Mapped[bool] = mapped_column(Boolean, default=False)
    sublet: Mapped[str] = mapped_column(Text, default="")
    max_people: Mapped[int | None] = mapped_column(Integer)
    lease_req: Mapped[str] = mapped_column(Text, default="")
    available: Mapped[str] = mapped_column(Text, default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    visits: Mapped[list] = mapped_column(JSONType, default=list)
    todos: Mapped[list] = mapped_column(JSONType, default=list)
    verify: Mapped[list] = mapped_column(JSONType, default=list)
    contract_id: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    workspace: Mapped[Workspace] = relationship(back_populates="houses")
    evidence: Mapped[list["HouseEvidence"]] = relationship(back_populates="house", cascade="all, delete-orphan")


class HouseEvidence(Base):
    __tablename__ = "house_evidence"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    house_id: Mapped[str] = mapped_column(ForeignKey("houses.id", ondelete="CASCADE"), index=True)
    field: Mapped[str] = mapped_column(String(32))
    snippet: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(16), default="paste")
    batch_id: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    house: Mapped[House] = relationship(back_populates="evidence")


# ==================== 偏好与推荐 ====================


class Preference(Base):
    __tablename__ = "preferences"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    budget: Mapped[int | None] = mapped_column(Integer)
    commute: Mapped[int | None] = mapped_column(Integer)
    need_bathroom: Mapped[bool] = mapped_column(Boolean, default=False)
    allow_shared: Mapped[bool] = mapped_column(Boolean, default=True)
    soft: Mapped[dict] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RecommendationRun(Base):
    __tablename__ = "recommendation_runs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    run_id: Mapped[str | None] = mapped_column(String(32))
    prefs_version: Mapped[int] = mapped_column(Integer, default=1)
    view: Mapped[str] = mapped_column(String(16), default="mix")
    snapshot: Mapped[dict] = mapped_column(JSONType, default=dict)  # 输入快照（房源 + 偏好），避免旧报告对新条件
    rankings: Mapped[dict] = mapped_column(JSONType, default=dict)  # budget/commute/mix 三视图
    explanation: Mapped[dict] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ==================== 合同与核验 ====================


class Contract(Base):
    __tablename__ = "contracts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    workspace_id: Mapped[str | None] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    house_id: Mapped[str | None] = mapped_column(String(32), index=True)
    no: Mapped[str] = mapped_column(String(16), default="C1")
    name: Mapped[str] = mapped_column(String(255), default="")
    filename: Mapped[str | None] = mapped_column(String(255))
    source_type: Mapped[str] = mapped_column(String(16), default="paste")  # paste|pdf|txt|docx
    size_label: Mapped[str] = mapped_column(String(32), default="")
    raw_text: Mapped[str] = mapped_column(Text, default="")
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    health_score: Mapped[int | None] = mapped_column(Integer)
    negotiation: Mapped[str | None] = mapped_column(Text)
    status: Mapped[ContractStatus] = mapped_column(
        String(16), default=ContractStatus.uploaded.value
    )
    storage_key: Mapped[str | None] = mapped_column(String(512))
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    workspace: Mapped[Workspace | None] = relationship(back_populates="contracts")
    clauses: Mapped[list["Clause"]] = relationship(back_populates="contract", cascade="all, delete-orphan")
    risks: Mapped[list["Risk"]] = relationship(back_populates="contract", cascade="all, delete-orphan")


class Clause(Base):
    __tablename__ = "clauses"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    contract_id: Mapped[str] = mapped_column(ForeignKey("contracts.id", ondelete="CASCADE"), index=True)
    clause_no: Mapped[int | None] = mapped_column(Integer, index=True)
    clause_type: Mapped[str] = mapped_column(String(32), default="其他")
    title: Mapped[str] = mapped_column(String(255), default="")
    raw_text: Mapped[str] = mapped_column(Text, default="")
    page: Mapped[int | None] = mapped_column(Integer)
    char_start: Mapped[int | None] = mapped_column(Integer)
    char_end: Mapped[int | None] = mapped_column(Integer)
    amount: Mapped[float | None] = mapped_column(Float)
    months: Mapped[int | None] = mapped_column(Integer)
    party_liable: Mapped[str | None] = mapped_column(String(16))
    extra: Mapped[dict | None] = mapped_column(JSONType)

    contract: Mapped[Contract] = relationship(back_populates="clauses")
    risks: Mapped[list["Risk"]] = relationship(back_populates="clause")


class Risk(Base):
    __tablename__ = "risks"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    contract_id: Mapped[str] = mapped_column(ForeignKey("contracts.id", ondelete="CASCADE"), index=True)
    clause_id: Mapped[str | None] = mapped_column(ForeignKey("clauses.id", ondelete="CASCADE"))
    level: Mapped[str] = mapped_column(String(8), default="low")
    rule_id: Mapped[str] = mapped_column(String(64), default="")
    title: Mapped[str] = mapped_column(String(255), default="")
    reason: Mapped[str] = mapped_column(Text, default="")
    suggestion: Mapped[str] = mapped_column(Text, default="")
    negotiation_script: Mapped[str | None] = mapped_column(Text)

    contract: Mapped[Contract] = relationship(back_populates="risks")
    clause: Mapped[Clause | None] = relationship(back_populates="risks")


class Verification(Base):
    __tablename__ = "verifications"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    house_id: Mapped[str] = mapped_column(String(32), index=True)
    contract_id: Mapped[str] = mapped_column(String(32), index=True)
    run_id: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), default="running")  # running|done|failed
    summary: Mapped[dict] = mapped_column(JSONType, default=dict)
    negotiation: Mapped[str] = mapped_column(Text, default="")
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    items: Mapped[list["VerificationItem"]] = relationship(
        back_populates="verification", cascade="all, delete-orphan"
    )


class VerificationItem(Base):
    __tablename__ = "verification_items"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    verification_id: Mapped[str] = mapped_column(ForeignKey("verifications.id", ondelete="CASCADE"), index=True)
    claim: Mapped[str] = mapped_column(Text, default="")
    field: Mapped[str] = mapped_column(String(32), default="")
    anchor: Mapped[str | None] = mapped_column(String(32))
    clause_id: Mapped[str | None] = mapped_column(String(32))
    clause_no: Mapped[int | None] = mapped_column(Integer)
    clause_text: Mapped[str] = mapped_column(Text, default="")
    page: Mapped[int | None] = mapped_column(Integer)
    char_start: Mapped[int | None] = mapped_column(Integer)
    char_end: Mapped[int | None] = mapped_column(Integer)
    result: Mapped[str] = mapped_column(String(8), default="无法判断")  # 一致|冲突|未约定|无法判断
    advice: Mapped[str] = mapped_column(Text, default="")
    severity: Mapped[str | None] = mapped_column(String(8))
    reason: Mapped[str] = mapped_column(Text, default="")

    verification: Mapped[Verification] = relationship(back_populates="items")


# ==================== 对话与运行 ====================


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(128), default="新对话")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    messages: Mapped[list["Message"]] = relationship(back_populates="conversation", cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(8), default="user")  # user|ai
    content: Mapped[dict] = mapped_column(JSONType, default=dict)
    citations: Mapped[list] = mapped_column(JSONType, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    workspace_id: Mapped[str | None] = mapped_column(String(32), index=True)
    thread_id: Mapped[str | None] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(24), default="")  # import|contract|recommend|verification|chat
    status: Mapped[str] = mapped_column(String(16), default=RunStatus.queued.value)
    progress: Mapped[dict] = mapped_column(JSONType, default=dict)
    result: Mapped[dict | None] = mapped_column(JSONType)
    error: Mapped[dict | None] = mapped_column(JSONType)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


__all__ = [
    "Clause",
    "Contract",
    "ContractStatus",
    "Conversation",
    "House",
    "HouseEvidence",
    "ImportBatch",
    "JSONType",
    "Message",
    "Preference",
    "RecommendationRun",
    "Risk",
    "RiskLevel",
    "Run",
    "RunStatus",
    "Verification",
    "VerificationItem",
    "Workspace",
    "uid",
    "utcnow",
]
