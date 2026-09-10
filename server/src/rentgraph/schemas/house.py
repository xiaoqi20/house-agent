"""房源导入与候选房源模型（字段组对齐 PRD §7 与 web/src/types.ts House）。"""

from typing import Any, Literal

from pydantic import BaseModel, Field

SourceKey = Literal["paste", "manual", "batch", "file-xlsx", "file-docx", "file-txt", "link"]


class HouseBase(BaseModel):
    name: str = ""
    region: str = ""
    address: str = ""
    rent: int | None = None
    deposit: str | None = None
    agency_fee: int | None = None
    property_fee: int | None = None
    property_bear: str = ""
    net_fee: int | None = None
    other_fee: str | int | None = None
    area: float | None = None
    layout: str = ""
    floor: str = ""
    orientation: str = ""
    bathroom: bool | None = None
    lighting: str = ""
    furniture: str = ""
    commute_min: int | None = None
    commute_mode: str = "地铁"
    metro: str = ""
    nearby: str = ""
    pet: str = ""
    shared: bool = False
    sublet: str = ""
    max_people: int | None = None
    lease_req: str = ""
    available: str = ""
    notes: str = ""
    link_url: str = ""


class HouseDraft(HouseBase):
    """AI 提取结果（未经用户确认，禁止进入推荐）。"""

    draft_id: str
    source: SourceKey = "paste"
    raw: str = ""
    confidence: float = 0.0
    evidence: dict[str, str] = Field(default_factory=dict, description="字段 → 原文片段")
    missing: list[str] = Field(default_factory=list, description="缺失/待确认字段中文名")
    duplicate_of: str | None = Field(default=None, description="疑似与已有候选重复时的房源 id")


class HouseConfirm(HouseBase):
    """用户在字段确认面板改过后的值。"""

    draft_id: str | None = None
    source: SourceKey = "paste"
    raw: str = ""
    evidence: dict[str, str] = Field(default_factory=dict)
    verify: list[str] = Field(default_factory=list)
    todos: list[str] = Field(default_factory=list)


class HouseCreate(HouseBase):
    source: SourceKey = "manual"
    raw: str = ""


class HousePatch(BaseModel):
    """局部更新：只允许改业务字段 / 备注 / 状态 / 清单。"""

    model_config = {"extra": "forbid"}

    name: str | None = None
    region: str | None = None
    address: str | None = None
    rent: int | None = None
    deposit: str | None = None
    agency_fee: int | None = None
    property_fee: int | None = None
    property_bear: str | None = None
    net_fee: int | None = None
    other_fee: str | int | None = None
    area: float | None = None
    layout: str | None = None
    floor: str | None = None
    orientation: str | None = None
    bathroom: bool | None = None
    lighting: str | None = None
    furniture: str | None = None
    commute_min: int | None = None
    commute_mode: str | None = None
    metro: str | None = None
    nearby: str | None = None
    pet: str | None = None
    shared: bool | None = None
    sublet: str | None = None
    max_people: int | None = None
    lease_req: str | None = None
    available: str | None = None
    notes: str | None = None
    link_url: str | None = None
    status: Literal["active", "dropped"] | None = None
    drop_reason: str | None = None
    todos: list[str] | None = None
    visits: list[dict[str, Any]] | None = None
    verify: list[str] | None = None


class HouseOut(HouseBase):
    id: str
    no: str
    batch_id: str | None = None
    status: Literal["active", "dropped"] = "active"
    drop_reason: str = ""
    source: SourceKey = "paste"
    raw: str = ""
    visits: list[dict[str, Any]] = Field(default_factory=list)
    todos: list[str] = Field(default_factory=list)
    verify: list[str] = Field(default_factory=list)
    contract_id: str | None = None
    source_label: str = ""
    completeness: int = 0
    missing: list[str] = Field(default_factory=list)
    evidence: dict[str, str] = Field(default_factory=dict)


_STR_FIELDS = (
    "name",
    "region",
    "address",
    "deposit",
    "property_bear",
    "layout",
    "floor",
    "orientation",
    "lighting",
    "furniture",
    "commute_mode",
    "metro",
    "nearby",
    "pet",
    "sublet",
    "lease_req",
    "available",
    "notes",
    "link_url",
    "raw",
)


def sanitize_draft(data: dict, *, source: str = "paste") -> dict:
    """模型/规则抽取结果 → HouseDraft 输入：null 统一成空串，缺 draft_id 自动补，忽略未知字段。"""

    import typing
    import uuid

    allowed = set(HouseDraft.model_fields)
    out = {key: value for key, value in dict(data).items() if key in allowed}
    for name, field in HouseDraft.model_fields.items():
        if name not in out or out[name] is not None:
            continue
        annotation = field.annotation
        if annotation is str:
            out[name] = ""  # 非可空文本字段：null → 空串（界面显示「待确认」而不是 None）
        elif annotation is bool:
            out.pop(name)  # 非可空布尔：用模型默认值，避免 LLM 返回 null 直接 500
        elif typing.get_origin(annotation) is typing.Union and str in typing.get_args(annotation):
            out[name] = ""
    out.setdefault("draft_id", uuid.uuid4().hex)
    out.setdefault("confidence", 0.0)
    out.setdefault("source", source or "paste")
    if not isinstance(out.get("evidence"), dict):
        out["evidence"] = {}
    if not isinstance(out.get("missing"), list):
        out["missing"] = []
    if not isinstance(out.get("visits"), list):
        out["visits"] = []
    if not isinstance(out.get("todos"), list):
        out["todos"] = []
    if not isinstance(out.get("verify"), list):
        out["verify"] = []
    return out


class BatchCreate(BaseModel):
    workspace_id: str
    source: Literal["paste", "manual", "batch", "link"] = "paste"
    text: str = ""
    link_url: str | None = None


class BatchOut(BaseModel):
    id: str
    workspace_id: str
    source: str
    status: str
    filename: str | None = None
    link_url: str | None = None
    raw_text: str | None = None
    drafts: list[HouseDraft] = Field(default_factory=list)
    house_count: int = 0
    error: dict[str, Any] | None = None
    run_id: str | None = None


class BatchConfirm(BaseModel):
    houses: list[HouseConfirm]


class BatchConfirmOut(BaseModel):
    houses: list[HouseOut]
    run_id: str | None = None
    hint: str = ""
