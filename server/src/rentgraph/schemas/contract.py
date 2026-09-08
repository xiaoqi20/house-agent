from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from ..models import ContractStatus, RiskLevel


class ContractCreate(BaseModel):
    text: str = Field(min_length=50, max_length=200_000, description="合同全文（粘贴）")
    filename: str | None = None


class ContractOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str | None
    source_type: str
    status: ContractStatus
    storage_key: str | None = None
    health_score: int | None
    error: str | None
    created_at: datetime


class ClauseRisk(BaseModel):
    """抽屉里一条条款可能命中多条规则（如押金条款），必须全列出来而不是只留最后一条"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    level: RiskLevel
    rule_id: str
    title: str
    reason: str
    suggestion: str
    negotiation_script: str | None = None


class ClauseView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    clause_no: int | None
    clause_type: str
    title: str
    raw_text: str
    is_risk: bool = False
    risks: list[ClauseRisk] = Field(default_factory=list)


class ContractTextView(BaseModel):
    contract_id: int
    filename: str | None
    clauses: list[ClauseView]


class RiskView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    level: RiskLevel
    clause_id: int
    clause_no: int | None = None
    clause_title: str | None = None
    rule_id: str
    title: str
    reason: str
    suggestion: str
    negotiation_script: str | None = None


class RisksSummary(BaseModel):
    contract_id: int
    filename: str | None = None
    health_score: int | None
    counts: dict[str, int]
    risks: list[RiskView]
