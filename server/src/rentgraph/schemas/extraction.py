from pydantic import BaseModel, Field

CLAUSE_TYPES = ["押金", "违约金", "租期", "租金", "维修", "续租", "解约", "转租", "其他"]


class ClauseData(BaseModel):
    clause_no: int | None = None
    clause_type: str = "其他"
    title: str
    raw_text: str = Field(min_length=4)
    amount: float | None = None
    months: int | None = None
    party_liable: str | None = None


class ClauseExtraction(BaseModel):
    """LLM 输出契约（S3 真实模型共用）"""

    clauses: list[ClauseData]
