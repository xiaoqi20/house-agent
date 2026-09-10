"""偏好：硬约束（淘汰）与软偏好（排序）必须分开（PRD §7.1）。"""

from pydantic import BaseModel, Field


class SoftPrefs(BaseModel):
    south: bool = False
    light: bool = False
    high_floor: bool = False
    big_area: bool = False
    flex_pay: bool = False


class PreferenceIn(BaseModel):
    budget: int | None = Field(default=None, ge=0, le=1_000_000, description="硬约束：月租上限（元）")
    commute: int | None = Field(default=None, ge=0, le=600, description="硬约束：通勤上限（分钟）")
    need_bathroom: bool = False
    allow_shared: bool = True
    soft: SoftPrefs = Field(default_factory=SoftPrefs)


class PreferenceOut(PreferenceIn):
    version: int = 1
