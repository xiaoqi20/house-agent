"""可解释推荐（P0-A 三视图）：只写解释，不碰排序。

数字后置校验（契约 §4.5）：解释文本里出现的金额/分钟/面积必须能在该房源的确定性
计算结果中找到，否则**整句剔除**——宁可少一句理由，也不给一个算不出来的数字。
"""

import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

from .mock import mock_explain
from .models import ExplanationItem, RecommendationExplanation
from .prompts import EXPLAIN_PROMPT
from .provider import LLMError, provider_mode, structured_call

_NUM_RE = re.compile(r"\d+(?:\.\d+)?")
_SEGMENTS = ("why", "tradeoffs", "risks", "todos", "next")


def ground_numbers(text: str, allowed_values: Sequence[float]) -> str | None:
    """句中数字必须全部来自确定性计算结果，否则返回 None（调用方剔除该句）"""
    allowed = [float(v) for v in allowed_values]
    for raw in _NUM_RE.findall(text):
        n = float(raw)
        if not any(abs(n - v) <= max(0.5, abs(v) * 0.01) for v in allowed):
            return None
    return text


def collect_numbers(*objs: Any) -> list[float]:
    """递归收集确定性结果里的全部数值（房源字段 / 偏好 / 排序项），作为允许值集合"""
    found: list[float] = []

    def walk(obj: Any) -> None:
        if isinstance(obj, bool) or obj is None:
            return
        if isinstance(obj, int | float):
            found.append(float(obj))
        elif isinstance(obj, str):
            try:
                found.append(float(obj))
            except ValueError:
                return
        elif isinstance(obj, Mapping):
            for v in obj.values():
                walk(v)
        elif isinstance(obj, list | tuple | set):
            for v in obj:
                walk(v)

    for obj in objs:
        walk(obj)
    return found


def _house_id(house: Mapping[str, Any]) -> str:
    hid = house.get("id")
    if hid is None or str(hid) == "":
        raise LLMError("HOUSE_ID_MISSING", "推荐解释缺少房源 id，无法与排序结果对应")
    return str(hid)


def _payload(
    houses: Sequence[Mapping[str, Any]],
    prefs: Mapping[str, Any],
    ranking_items: Mapping[str, Mapping[str, Any]],
) -> str:
    data = {
        "prefs": dict(prefs),
        "houses": [{k: v for k, v in h.items() if k not in ("raw", "evidence")} for h in houses],
        "ranking_items": {str(k): dict(v) for k, v in ranking_items.items()},
    }
    payload = json.dumps(data, ensure_ascii=False, default=str)
    return f"{EXPLAIN_PROMPT}\n\n确定性计算结果（JSON）：\n{payload}"


def ground_explanation(
    result: RecommendationExplanation,
    houses: Sequence[Mapping[str, Any]],
    prefs: Mapping[str, Any],
    ranking_items: Mapping[str, Mapping[str, Any]],
) -> RecommendationExplanation:
    """按房源过滤：只保留输入里存在的 house_id，逐句做数字校验，不通过就丢弃该句"""
    items: dict[str, ExplanationItem] = {}
    for house in houses:
        hid = _house_id(house)
        item = result.items.get(hid) or ExplanationItem()
        allowed = collect_numbers(house, prefs, ranking_items.get(hid) or {})
        items[hid] = ExplanationItem(
            **{
                seg: [kept for s in getattr(item, seg) if (kept := ground_numbers(s, allowed))]
                for seg in _SEGMENTS
            }
        )
    return RecommendationExplanation(items=items)


async def explain_recommendation(
    houses: Sequence[Mapping[str, Any]],
    prefs: Mapping[str, Any],
    ranking_items: Mapping[str, Mapping[str, Any]],
) -> RecommendationExplanation:
    """五段解释（PRD §8）。houses = 房源字段；ranking_items = house_id → 确定性排序项"""
    if not houses:
        raise LLMError("NO_HOUSES", "没有房源可解释：请先确认候选房源再生成推荐")
    if provider_mode() == "mock":
        result = mock_explain(houses, prefs, ranking_items)
    else:
        result = await structured_call(RecommendationExplanation, _payload(houses, prefs, ranking_items))
    return ground_explanation(result, houses, prefs, ranking_items)


__all__ = ["collect_numbers", "explain_recommendation", "ground_explanation", "ground_numbers"]
