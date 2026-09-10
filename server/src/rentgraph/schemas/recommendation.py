"""推荐结果：确定性排序 + LLM 解释（数字不得由模型生成）。"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from .house import HouseOut
from .preference import PreferenceOut

RecView = Literal["mix", "budget", "commute"]
Verdict = Literal["优先考虑", "可作为备选", "不建议"]


class RankItemOut(BaseModel):
    house_id: str
    rank: int
    monthly_cost: int
    monthly_cost_unknown: list[str] = Field(default_factory=list)
    one_time_cost: int
    one_time_label: str = ""
    hard_violations: list[str] = Field(default_factory=list)
    soft_hits: list[str] = Field(default_factory=list)
    soft_miss: list[str] = Field(default_factory=list)
    verdict: Verdict = "可作为备选"
    comparable: bool = True
    tie_break_note: str = ""


class ViewRanking(BaseModel):
    order: list[str] = Field(default_factory=list, description="house_id 顺序")
    items: dict[str, RankItemOut] = Field(default_factory=dict)


class ExplanationOut(BaseModel):
    why: list[str] = Field(default_factory=list)
    tradeoffs: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    todos: list[str] = Field(default_factory=list)
    next: list[str] = Field(default_factory=list)


class RecommendationOut(BaseModel):
    id: str
    prefs_version: int = 1
    view: RecView = "mix"
    created_at: datetime | None = None
    snapshot: dict[str, Any] = Field(default_factory=dict, description="{houses:[HouseOut], prefs:PreferenceOut}")
    views: dict[str, ViewRanking] = Field(default_factory=dict)
    explanation: dict[str, ExplanationOut] = Field(default_factory=dict)
    about: dict[str, Any] = Field(default_factory=dict, description="硬约束/软偏好/缺失字段说明")


class RecommendationCreate(BaseModel):
    workspace_id: str
    view: RecView = "mix"


class RecommendationCreated(BaseModel):
    recommendation_id: str
    run_id: str


class RecommendationSnapshot(BaseModel):
    houses: list[HouseOut] = Field(default_factory=list)
    prefs: PreferenceOut
