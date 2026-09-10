"""合同模型（沿用一期合同风险雷达的条款/风险结构，补齐 v1.1 的房源绑定与原文定位）。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

ContractStatusLiteral = Literal["uploaded", "parsing", "analyzing", "done", "failed"]


class ContractCreate(BaseModel):
    workspace_id: str
    house_id: str | None = None
    text: str = Field(min_length=1, max_length=200_000, description="合同全文（粘贴）")
    name: str | None = None


class ClauseRisk(BaseModel):
    id: str
    level: Literal["high", "medium", "low"]
    rule_id: str
    title: str
    reason: str
    suggestion: str
    negotiation_script: str | None = None


class ClauseView(BaseModel):
    id: str
    clause_no: int | None = None
    clause_type: str = "其他"
    title: str = ""
    raw_text: str = ""
    page: int | None = None
    char_start: int | None = None
    char_end: int | None = None
    is_risk: bool = False
    risks: list[ClauseRisk] = Field(default_factory=list)


class ContractTextView(BaseModel):
    contract_id: str
    filename: str | None = None
    clauses: list[ClauseView]


class RiskView(BaseModel):
    id: str
    level: Literal["high", "medium", "low"]
    clause_id: str | None = None
    clause_no: int | None = None
    clause_title: str | None = None
    rule_id: str
    title: str
    reason: str
    suggestion: str
    negotiation_script: str | None = None


class RisksSummary(BaseModel):
    contract_id: str
    filename: str | None = None
    health_score: int | None = None
    counts: dict[str, int] = Field(default_factory=dict)
    risks: list[RiskView] = Field(default_factory=list)


class ContractOut(BaseModel):
    """与前端 web/src/types.ts 的 Contract 同构（clauses_list 为 [条号, 标题, 原文] 元组）。"""

    id: str
    no: str
    name: str
    source: str
    time: str
    status: ContractStatusLiteral
    reason: str = ""
    size: str = ""
    bound_house_id: str | None = None
    clauses_list: list[tuple[int | None, str, str]] = Field(default_factory=list)
    risk_clauses: list[int] = Field(default_factory=list)
    negotiation: str = ""
    health_score: int | None = None
    page_count: int = 0
    created_at: datetime | None = None
