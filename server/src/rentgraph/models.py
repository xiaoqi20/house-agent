import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class ContractStatus(str, enum.Enum):
    uploaded = "uploaded"
    analyzing = "analyzing"
    done = "done"
    failed = "failed"


class RiskLevel(str, enum.Enum):
    high = "high"
    medium = "medium"
    low = "low"


class Contract(Base):
    __tablename__ = "contracts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    filename: Mapped[str | None] = mapped_column(String(255))
    source_type: Mapped[str] = mapped_column(String(16), default="paste")  # paste | pdf
    raw_text: Mapped[str] = mapped_column(Text)
    health_score: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[ContractStatus] = mapped_column(
        Enum(ContractStatus, native_enum=False, length=16), default=ContractStatus.uploaded
    )
    storage_key: Mapped[str | None] = mapped_column(String(512))  # LocalStorage key，二期换 OSS 同字段
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    clauses: Mapped[list["Clause"]] = relationship(back_populates="contract", cascade="all, delete-orphan")
    risks: Mapped[list["Risk"]] = relationship(back_populates="contract", cascade="all, delete-orphan")


class Clause(Base):
    __tablename__ = "clauses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    contract_id: Mapped[int] = mapped_column(ForeignKey("contracts.id", ondelete="CASCADE"), index=True)
    clause_no: Mapped[int | None] = mapped_column(Integer)
    clause_type: Mapped[str] = mapped_column(String(32))  # 押金/违约金/租期/维修/续约/解约/其他
    title: Mapped[str] = mapped_column(String(128))
    raw_text: Mapped[str] = mapped_column(Text)
    amount: Mapped[float | None] = mapped_column(Float)
    months: Mapped[int | None] = mapped_column(Integer)
    party_liable: Mapped[str | None] = mapped_column(String(16))
    extra: Mapped[dict | None] = mapped_column(JSONB)

    contract: Mapped[Contract] = relationship(back_populates="clauses")
    risks: Mapped[list["Risk"]] = relationship(back_populates="clause")


class Risk(Base):
    __tablename__ = "risks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    contract_id: Mapped[int] = mapped_column(ForeignKey("contracts.id", ondelete="CASCADE"), index=True)
    clause_id: Mapped[int] = mapped_column(ForeignKey("clauses.id", ondelete="CASCADE"))
    level: Mapped[RiskLevel] = mapped_column(Enum(RiskLevel, native_enum=False, length=8))
    rule_id: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(128))
    reason: Mapped[str] = mapped_column(Text)
    suggestion: Mapped[str] = mapped_column(Text)
    negotiation_script: Mapped[str | None] = mapped_column(Text)

    contract: Mapped[Contract] = relationship(back_populates="risks")
    clause: Mapped["Clause"] = relationship(back_populates="risks")
