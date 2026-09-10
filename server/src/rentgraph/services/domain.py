"""确定性领域核心：成本 / 完整度 / 硬约束 / 三视图排序（契约 §4.5、PRD §3.2 §8 §10 场景 1）。

纯函数逐字移植自前端 `web/src/lib/calc.ts`、`web/src/lib/recommend.ts` 与
`web/src/components/cards/RecommendCard.tsx`：后端接线后已验收 UI 的数字与文案必须不变，
所以金额口径、软偏好命中/缺失文案、排序键都与前端一致（可复算、可解释）。无 DB、无 async、无 LLM。

字段命名：对外统一用前端 camelCase 名（`rent` / `propertyFee` / `commuteMin` …）。
`normalise_house` / `normalise_prefs` 同时接受 snake_case（DB 列名 `property_fee` / `commute_min`）
与对象属性（ORM 行），因此 dict、JSON、ORM 行都能直接传入。

从 RecommendCard.tsx 推导出的推荐状态映射（`verdict`）：
- 有硬约束违反 → 「不建议」（前端 fail 区块 FailRow，不进入 pass 列表）；
- 无违反但不可比（关键字段缺失，或合租但用户未接受合租）→ 「可作为备选」
  （前端「待完善候选」「未纳入合租」区块，永不冒充「优先考虑」）；
- 可比且无违反：排序首位 → 「优先考虑」，其余 → 「可作为备选」
  （前端 `pass.map((r, i) => i === 0 ? 'top' : 'alt')` 只区分首位与其余，没有 rank>=3 之类的阈值）。

前端语义有两处未定义、由本模块显式补齐并记录：
1. 前端对可比房源分 pass/fail 两块渲染，块内顺序与三视图排序键不完全一致；后端返回单一有序列表，
   由 `verdict` 区分两块，排序键严格按契约 §4.5/§10 场景 1 给出；
2. 不可比房源（待完善 / 未接受合租）前端另起区块；后端统一排在可比集合之后，但仍在同一列表内，
   带 `comparable=False` 与原因，避免静默丢弃。
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

# ---------- 输入归一化 ----------

# 前端 camelCase 名 → 实际可能出现的键名（含 DB snake_case 列名）
_ALIASES: dict[str, tuple[str, ...]] = {
    "id": ("id", "house_id"),
    "no": ("no",),
    "name": ("name",),
    "status": ("status",),
    "source": ("source",),
    "region": ("region",),
    "rent": ("rent",),
    "deposit": ("deposit",),
    "agencyFee": ("agencyFee", "agency_fee"),
    "propertyFee": ("propertyFee", "property_fee"),
    "propertyBear": ("propertyBear", "property_bear"),
    "netFee": ("netFee", "net_fee"),
    "otherFee": ("otherFee", "other_fee"),
    "area": ("area",),
    "layout": ("layout",),
    "floor": ("floor",),
    "orientation": ("orientation",),
    "bathroom": ("bathroom",),
    "lighting": ("lighting",),
    "commuteMin": ("commuteMin", "commute_min"),
    "pet": ("pet",),
    "shared": ("shared",),
    "sublet": ("sublet",),
    "maxPeople": ("maxPeople", "max_people"),
    "leaseReq": ("leaseReq", "lease_req"),
    "available": ("available",),
}

_NUMERIC = ("rent", "agencyFee", "propertyFee", "netFee", "area", "commuteMin", "maxPeople")

_SOFT_ALIASES: dict[str, tuple[str, ...]] = {
    "south": ("south",),
    "light": ("light",),
    "highFloor": ("highFloor", "high_floor"),
    "bigArea": ("bigArea", "big_area"),
    "flexPay": ("flexPay", "flex_pay"),
}


class DomainError(ValueError):
    """领域规则无法完成时抛出（带错误码，接口层直接映射错误体，不静默猜测）。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def raw_value(obj: Mapping[str, Any] | object, *names: str) -> Any:
    """按顺序取第一个存在且非 None 的值：兼容 Mapping（dict/JSON）与对象属性（ORM 行）。"""
    for name in names:
        if isinstance(obj, Mapping):
            if name in obj and obj[name] is not None:
                return obj[name]
        elif hasattr(obj, name):
            value = getattr(obj, name)
            if value is not None:
                return value
    return None


def _num(value: Any) -> int | float | None:
    """数值字段归一化：''/None/布尔 → None；整数值返回 int（与前端数字语义一致）。"""
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return int(number) if number.is_integer() else number


def format_amount(value: Any) -> str:
    """金额千分位（对齐前端 `fmt` = Number(n).toLocaleString()），用于硬约束文案与核验话术。"""
    if value is None or value == "":
        return ""
    number = _num(value)
    if number is None:
        return str(value)
    if isinstance(number, int):
        return f"{number:,}"
    return f"{number:,}"


def normalise_house(raw: Mapping[str, Any] | object) -> dict[str, Any]:
    """房源归一化：统一产出 camelCase 键，缺失字段为 None（0/'' 不冒充已确认值）。"""
    house: dict[str, Any] = {name: raw_value(raw, *names) for name, names in _ALIASES.items()}
    for key in _NUMERIC:
        house[key] = _num(house[key])
    if house["shared"] is not None:
        house["shared"] = bool(house["shared"])
    return house


@dataclass(frozen=True)
class Prefs:
    """偏好（硬约束 + 软偏好），字段名与前端 `Preferences` 对齐。"""

    budget: int | float | None
    commute: int | float | None
    need_bathroom: bool
    allow_shared: bool
    soft: Mapping[str, bool]


def normalise_prefs(raw: Mapping[str, Any] | object) -> Prefs:
    """偏好归一化：`needBathroom/need_bathroom`、`allowShared/allow_shared`、`soft.*` 均可。"""
    soft_raw = raw_value(raw, "soft") or {}
    soft = {name: bool(raw_value(soft_raw, *names)) for name, names in _SOFT_ALIASES.items()}
    return Prefs(
        budget=_num(raw_value(raw, "budget")),
        commute=_num(raw_value(raw, "commute")),
        need_bathroom=bool(raw_value(raw, "needBathroom", "need_bathroom")),
        allow_shared=bool(raw_value(raw, "allowShared", "allow_shared")),
        soft=soft,
    )


# ---------- 完整度 / 成本（web/src/lib/calc.ts） ----------

# 关键字段清单（用于完整度 / 缺失计算），顺序与中文标签与前端逐字一致
KEY_FIELDS: tuple[tuple[str, str], ...] = (
    ("rent", "租金"),
    ("deposit", "押金/付款方式"),
    ("propertyFee", "物业费"),
    ("commuteMin", "通勤"),
    ("layout", "户型"),
    ("area", "面积"),
    ("floor", "楼层"),
    ("orientation", "朝向"),
    ("bathroom", "独立卫浴"),
    ("available", "可入住时间"),
    ("pet", "宠物"),
    ("region", "区域"),
)


def _filled(house: dict[str, Any], key: str) -> bool:
    value = house.get(key)
    if key == "bathroom":
        return value is True or value is False  # 明确「无独卫」也算已确认
    return value is not None and value != ""


def is_filled(house: Mapping[str, Any] | object, key: str) -> bool:
    """字段是否已确认填写（bathroom 的 False 视为已填写）。"""
    return _filled(normalise_house(house), key)


def missing_fields(house: Mapping[str, Any] | object) -> list[str]:
    """缺失关键字段的中文标签，顺序同 KEY_FIELDS（供 UI 展示「信息风险」）。"""
    h = normalise_house(house)
    return [label for key, label in KEY_FIELDS if not _filled(h, key)]


def completeness(house: Mapping[str, Any] | object) -> int:
    """信息完整度百分比（0-100，四舍五入同前端 Math.round）。"""
    h = normalise_house(house)
    filled = sum(1 for key, _ in KEY_FIELDS if _filled(h, key))
    return int(math.floor(filled / len(KEY_FIELDS) * 100 + 0.5))


@dataclass(frozen=True)
class MonthlyCost:
    """月度总成本：月租 + 物业费 + 网费；缺失项进 `unknown`（UI 显示「≈」与「待确认」）。"""

    sum: int
    unknown: list[str]
    is_rent_missing: bool


@dataclass(frozen=True)
class OneTimeCost:
    """一次性支出：押金（押 X 月 × 月租）+ 中介费；`label` 为押金原文，空则为「待确认」。"""

    deposit: int
    agency: int | float | None
    label: str


def monthly_cost(house: Mapping[str, Any] | object) -> MonthlyCost:
    """月度总成本：月租 + 物业费 + 网费；缺失的固定费用不按 0 计入，而是列入 unknown。"""
    h = normalise_house(house)
    unknown: list[str] = []
    rent = h["rent"]
    total = int(rent) if rent is not None else 0
    if rent is None:
        unknown.append("租金")
    for key, label in (("propertyFee", "物业费"), ("netFee", "网费")):
        value = h[key]
        if value is not None:
            total += int(value)
        else:
            unknown.append(label)
    return MonthlyCost(sum=total, unknown=unknown, is_rent_missing=rent is None)


def one_time_cost(house: Mapping[str, Any] | object) -> OneTimeCost:
    """一次性支出 = 押金 + 中介费。押金月数只认「押X付」里的 X（与前端一致，押一付三只算 1 个月）。"""
    h = normalise_house(house)
    deposit_text = "" if h["deposit"] is None else str(h["deposit"])
    match = re.search(r"押([一二三])付", deposit_text)
    months = {"一": 1, "二": 2, "三": 3}.get(match.group(1), 0) if match else 0
    rent = h["rent"] or 0
    return OneTimeCost(deposit=int(rent * months), agency=h["agencyFee"], label=deposit_text or "待确认")


def comparison_missing_fields(
    house: Mapping[str, Any] | object, prefs: Mapping[str, Any] | object
) -> list[str]:
    """参与推荐比较所必需的关键字段（租金 / 通勤 / 独立卫浴，独卫仅当偏好要求时必须）。"""
    h = normalise_house(house)
    p = normalise_prefs(prefs)
    missing: list[str] = []
    if h["rent"] is None:
        missing.append("租金")
    if h["commuteMin"] is None:
        missing.append("通勤")
    if p.need_bathroom and h["bathroom"] is not True and h["bathroom"] is not False:
        missing.append("独立卫浴")
    return missing


# ---------- 硬约束 / 软偏好（web/src/lib/recommend.ts） ----------


def hard_violations(house: Mapping[str, Any] | object, prefs: Mapping[str, Any] | object) -> list[str]:
    """硬约束违反项，文案与前端 `hardCheck` 逐字一致（空数组 = 满足全部硬约束）。"""
    h = normalise_house(house)
    p = normalise_prefs(prefs)
    violations: list[str] = []
    if h["rent"] is None:
        violations.append("月租缺失（关键硬约束无法验证，不可直接推荐）")
    elif p.budget is not None and h["rent"] > p.budget:
        violations.append(f"月租 {format_amount(h['rent'])} 超出预算 {format_amount(p.budget)}")
    if h["commuteMin"] is None:
        violations.append("通勤时间缺失（关键硬约束无法验证，不可直接推荐）")
    elif p.commute is not None and h["commuteMin"] > p.commute:
        violations.append(f"通勤 {h['commuteMin']} 分钟超出上限 {p.commute} 分钟")
    if p.need_bathroom and h["bathroom"] is not True:
        if h["bathroom"] is False:
            violations.append("无独立卫浴（硬约束不满足）")
        else:
            violations.append("独立卫浴情况待确认（硬约束无法验证）")
    return violations


@dataclass(frozen=True)
class SoftScore:
    """软偏好命中/未命中与得分（score = 命中数，只影响排序，并在卡片里说明取舍）。"""

    hits: list[str]
    miss: list[str]
    score: int


def _leading_int(value: Any) -> int | None:
    """取字符串开头的整数（对齐前端 parseInt('12/18层') === 12）。"""
    if value is None or value == "":
        return None
    match = re.match(r"\s*(-?\d+)", str(value))
    return int(match.group(1)) if match else None


def soft_score(house: Mapping[str, Any] | object, prefs: Mapping[str, Any] | object) -> SoftScore:
    """软偏好评分：南向 / 采光好 / 中高楼层(≥6) / 面积≥50㎡ / 付款灵活(付一)。"""
    h = normalise_house(house)
    soft = normalise_prefs(prefs).soft
    hits: list[str] = []
    miss: list[str] = []

    def record(hit: bool, hit_text: str, miss_text: str) -> None:
        (hits if hit else miss).append(hit_text if hit else miss_text)

    if soft.get("south"):
        record("南" in str(h["orientation"] or ""), "南向", "非南向")
    if soft.get("light"):
        record("好" in str(h["lighting"] or ""), "采光好", "采光未确认")
    if soft.get("highFloor"):
        floor = _leading_int(h["floor"])
        record(floor is not None and floor >= 6, "中高楼层", "楼层偏低")
    if soft.get("bigArea"):
        area = h["area"]
        record(area is not None and float(area) >= 50, f"面积 {area}㎡", "面积不大")
    if soft.get("flexPay"):
        record("付一" in str(h["deposit"] or ""), "付款灵活", "付款压力大")
    return SoftScore(hits=hits, miss=miss, score=len(hits))


# ---------- 推荐状态 / 三视图排序 ----------

SOURCE_LABEL: dict[str, str] = {
    "paste": "用户粘贴",
    "manual": "手动填写",
    "batch": "批量粘贴",
    "file-xlsx": "Excel 导入",
    "file-docx": "Word 导入",
    "file-txt": "文本文件导入",
    "link": "外部链接",
}

VIEWS: tuple[str, ...] = ("budget", "commute", "mix")

_VIEW_LABEL = {"budget": "按预算", "commute": "按通勤", "mix": "综合匹配"}
_SORT_LABEL: dict[str, tuple[str, ...]] = {
    "budget": ("月度成本", "通勤", "信息完整度", "房源编号"),
    "commute": ("通勤", "月度成本", "软偏好", "房源编号"),
    "mix": ("硬约束违反项", "软偏好", "月度成本", "通勤", "房源编号"),
}


@dataclass(frozen=True)
class RankItem:
    """三视图中的一行：全字段可复算，前端只负责渲染。"""

    house_id: str
    rank: int  # 1-based，与返回列表顺序一致
    monthly_cost: int
    one_time_cost: int
    hard_violations: list[str]
    soft_hits: list[str]
    soft_miss: list[str]
    verdict: str
    comparable: bool
    tie_break_note: str


def verdict(rank_index: int, violations: Sequence[str], missing: Sequence[str]) -> str:
    """推荐状态（0-based rank_index，映射来源见模块 docstring 的 RecommendCard.tsx 推导）。"""
    if violations:
        return "不建议"
    if missing:
        return "可作为备选"
    return "优先考虑" if rank_index == 0 else "可作为备选"


def _shared_out(house: dict[str, Any], prefs: Prefs) -> bool:
    """合租房源但用户未接受合租：前端单独区块，不参与推荐比较。"""
    return bool(house["shared"]) and not prefs.allow_shared


def _is_active(house: dict[str, Any]) -> bool:
    return house["status"] in (None, "", "active")


def _commute_key(house: dict[str, Any]) -> float:
    value = house["commuteMin"]
    return float("inf") if value is None else float(value)


def _cost_key(house: dict[str, Any]) -> int:
    return monthly_cost(house).sum


def _view_key(view: str, house: dict[str, Any], prefs: Prefs) -> tuple[Any, ...]:
    no = str(house["no"] or "")
    if view == "budget":
        cost = monthly_cost(house)
        return (1 if cost.is_rent_missing else 0, cost.sum, _commute_key(house), -completeness(house), no)
    if view == "commute":
        return (_commute_key(house), _cost_key(house), -soft_score(house, prefs).score, no)
    violations = hard_violations(house, prefs)
    return (
        len(violations),
        -soft_score(house, prefs).score,
        _cost_key(house),
        _commute_key(house),
        no,
    )


def _tie_break_note(view: str, current: tuple[Any, ...], previous: tuple[Any, ...] | None) -> str:
    labels = _SORT_LABEL[view]
    if previous is None:
        return f"{labels[0]}最优（排序方向：{_VIEW_LABEL[view]}）"
    for index, (now, before) in enumerate(zip(current, previous, strict=True)):
        if now != before:
            return f"{labels[index]}更优" if now < before else f"{labels[index]}并列后仍靠前"
    return "与上一名各排序键相同，按录入顺序稳定排列"


def rank_views(
    houses: Sequence[Mapping[str, Any] | object], prefs: Mapping[str, Any] | object, view: str
) -> list[RankItem]:
    """三视图排序（契约 §4.5）：可比集合在前、不可比集合在后，均带可比性与排序理由。

    - budget：月度成本升序（租金缺失置后）→ 通勤升序 → 完整度降序 → 编号升序
    - commute：通勤升序（缺失置后）→ 月度成本升序 → 软偏好得分降序 → 编号升序
    - mix：硬约束违反数升序 → 软偏好得分降序 → 月度成本升序 → 通勤升序 → 编号升序

    不可比房源（关键字段缺失 / 未接受合租）不会被静默丢弃，也不会冒充「优先考虑」，
    它们保留在列表末尾，`comparable=False` 且 `tie_break_note` 说明原因（PRD §8 要求完整度与待核实可见）。
    """
    if view not in VIEWS:
        raise DomainError("DOMAIN_UNKNOWN_VIEW", f"未知排序视角：{view}")
    p = normalise_prefs(prefs)
    rows: list[dict[str, Any]] = []
    for raw in houses:
        house = normalise_house(raw)
        if not _is_active(house):
            continue
        reasons = list(comparison_missing_fields(house, p))
        if _shared_out(house, p):
            reasons.append("合租房源（当前偏好不接受合租）")
        rows.append({"house": house, "reasons": reasons, "comparable": not reasons})
    rows.sort(key=lambda row: (0 if row["comparable"] else 1, _view_key(view, row["house"], p)))

    items: list[RankItem] = []
    previous: tuple[Any, ...] | None = None
    for index, row in enumerate(rows):
        house = row["house"]
        keys = _view_key(view, house, p)
        one_time = one_time_cost(house)
        soft = soft_score(house, p)
        violations = hard_violations(house, p)
        if row["comparable"]:
            note = _tie_break_note(view, keys, previous)
        else:
            note = "不可比，未纳入本次推荐比较：缺少 " + "、".join(row["reasons"])
        items.append(
            RankItem(
                house_id=str(house["id"]),
                rank=index + 1,
                monthly_cost=_cost_key(house),
                one_time_cost=int(one_time.deposit + (one_time.agency or 0)),
                hard_violations=violations,
                soft_hits=soft.hits,
                soft_miss=soft.miss,
                verdict=verdict(index, violations, row["reasons"]),
                comparable=row["comparable"],
                tie_break_note=note,
            )
        )
        previous = keys
    return items


def check_compare_window(houses: Sequence[Mapping[str, Any] | object]) -> dict[str, Any]:
    """3—10 套比较窗口校验（PRD §7.1.1）：<3 提示继续添加，>10 要求拆分或移除。"""
    count = sum(1 for raw in houses if _is_active(normalise_house(raw)))
    if count < 3:
        return {
            "count": count,
            "ok": False,
            "message": f"当前 {count} 套候选，少于 3 套无法比较，请继续添加房源",
        }
    if count > 10:
        return {
            "count": count,
            "ok": False,
            "message": f"当前 {count} 套候选，超过 10 套，请拆分批次或移除部分房源后再比较",
        }
    return {"count": count, "ok": True, "message": f"当前 {count} 套候选，在 3—10 套比较区间内"}
