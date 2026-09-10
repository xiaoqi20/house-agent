"""房源承诺 × 合同条款核验（PRD §3.3、场景 2）。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

VerifyResult = Literal["一致", "冲突", "未约定", "无法判断"]
Severity = Literal["high", "medium", "low"]


class VerificationCreate(BaseModel):
    workspace_id: str
    house_id: str
    contract_id: str


class VerificationItemOut(BaseModel):
    id: str
    claim: str
    field: str
    anchor: str | None = None
    clause_id: str | None = None
    clause_no: int | None = None
    clause_text: str = ""
    page: int | None = None
    char_start: int | None = None
    char_end: int | None = None
    result: VerifyResult = "无法判断"
    advice: str = ""
    severity: Severity | None = None
    reason: str = ""


class VerificationOut(BaseModel):
    id: str
    house_id: str
    contract_id: str
    status: Literal["running", "done", "failed"] = "running"
    summary: dict = Field(default_factory=dict)
    items: list[VerificationItemOut] = Field(default_factory=list)
    negotiation: str = ""
    error: str | None = None
    created_at: datetime | None = None
    run_id: str | None = None
