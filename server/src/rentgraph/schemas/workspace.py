"""工作台（一期临时数据边界）。"""

from datetime import datetime

from pydantic import BaseModel


class WorkspaceOut(BaseModel):
    id: str
    title: str
    created_at: datetime
    expires_at: datetime
    house_count: int = 0
    contract_count: int = 0
    ctx_house_id: str | None = None
    ctx_contract_id: str | None = None


class CtxUpdate(BaseModel):
    """当前上下文：主房源 0/1 个 + 可选合同 0/1 个（PRD §9.1）。"""

    house_id: str | None = None
    contract_id: str | None = None
