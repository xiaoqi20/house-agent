"""流程 A：可解释推荐。

排名/成本/硬约束全部用 `services/domain.py` 的确定性函数；LLM 只写解释，且解释里的数字
必须能在计算结果中找到（PRD §8、选型 §6.2）。每次推荐保存输入快照，避免旧报告对应新条件。
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, is_dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ...db import SessionLocal
from ...errors import AppError
from ...models import House, Preference, RecommendationRun, Workspace
from .. import engine
from ..convert import house_out, house_to_dict
from ..runs import RunContext

DEFAULT_SOFT = {"south": False, "light": False, "high_floor": False, "big_area": False, "flex_pay": False}


async def load_prefs(db, workspace_id: str) -> dict[str, Any]:
    row = (
        await db.execute(
            select(Preference).where(Preference.workspace_id == workspace_id).order_by(Preference.version.desc())
        )
    ).scalars().first()
    if row is None:
        return {
            "version": 1,
            "budget": None,
            "commute": None,
            "need_bathroom": False,
            "allow_shared": True,
            "soft": dict(DEFAULT_SOFT),
        }
    return {
        "version": row.version,
        "budget": row.budget,
        "commute": row.commute,
        "need_bathroom": row.need_bathroom,
        "allow_shared": row.allow_shared,
        "soft": {**DEFAULT_SOFT, **(row.soft or {})},
    }


async def run_recommendation(run: RunContext, recommendation_id: str) -> dict[str, Any]:
    async with SessionLocal() as db:
        rec = await db.get(RecommendationRun, recommendation_id)
        if rec is None:
            raise AppError("NOT_FOUND", "推荐任务不存在")
        pref_row = await load_prefs(db, rec.workspace_id)
        houses = list(
            (
                await db.execute(
                    select(House)
                    .where(House.workspace_id == rec.workspace_id, House.status == "active")
                    .options(selectinload(House.evidence))
                    .order_by(House.no)
                )
            ).scalars()
        )
        await run.progress("rank", 0, "硬约束过滤与成本计算", "active")
        if not houses:
            raise AppError("NO_DRAFTS", "本次工作台还没有候选房源", "先导入或手动添加 3—10 套房源")

        window = engine.check_compare_window(houses)
        house_dicts = [house_to_dict(house) for house in houses]
        rankings = engine.rank_views(house_dicts, pref_row)

        snapshot = {
            "houses": [json.loads(house_out(house).model_dump_json()) for house in houses],
            "prefs": pref_row,
        }
        rec.snapshot = snapshot
        rec.prefs_version = int(pref_row.get("version") or 1)
        rec.view = rec.view or "mix"
        rec.rankings = _serializable(rankings)
        await db.commit()
        await run.progress("rank", 0, f"完成 {len(houses)} 套候选的硬约束与成本计算", "done")

        run.check_cancelled()
        await run.progress("explain", 1, "生成推荐依据、取舍与待确认", "active")
        mix_items = _items_of(rankings, "mix")
        explanation = await engine.explain_recommendation(house_dicts, pref_row, mix_items)
        rec.explanation = _serializable(explanation)
        await db.commit()

        text = _explanation_text(house_dicts, explanation)
        for chunk in _chunks(text, 48):
            await run.token(chunk)
        await run.progress("explain", 1, "推荐依据生成完成", "done")

        about = {
            "hard_rules": _hard_rule_lines(pref_row),
            "soft_rules": _soft_rule_lines(pref_row),
            "window": window,
            "missing": [
                f"{house.no}：{'、'.join(engine.missing_fields(house_dicts[i]))}"
                for i, house in enumerate(houses)
                if engine.missing_fields(house_dicts[i])
            ],
        }
        from ...schemas.recommendation import RecommendationOut

        payload = RecommendationOut(
            id=rec.id,
            prefs_version=rec.prefs_version,
            view=rec.view,
            created_at=rec.created_at,
            snapshot=snapshot,
            views={key: _view_model(value) for key, value in _serializable(rankings).items()},
            explanation=_explanation_model(explanation),
            about=about,
        )
        return json.loads(payload.model_dump_json())


def _serializable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    if isinstance(value, dict):
        return {key: _serializable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serializable(item) for item in value]
    return value


def _items_of(rankings: Any, view: str) -> list[Any]:
    if isinstance(rankings, dict):
        return list(rankings.get(view) or [])
    return list(rankings or [])


def _view_model(value: Any) -> Any:
    """RankItem(dataclass) 列表 → ViewRanking（order + items 映射）。"""

    from ...schemas.recommendation import RankItemOut, ViewRanking

    raw = _serializable(value)
    if isinstance(raw, dict):
        return ViewRanking(**raw)
    items = [RankItemOut(**item) for item in raw]
    return ViewRanking(order=[item.house_id for item in items], items={item.house_id: item for item in items})


def _explanation_model(value: Any) -> dict[str, Any]:
    """RecommendationExplanation / 持久化 JSON → {house_id: ExplanationOut}。

    LLM 层返回的是 {"items": {house_id: {...}}}（pydantic 包装），契约 §4.5 要求直接以
    house_id 为键，这里统一拆包，避免前端 explanation[house_id] 取到 undefined。
    """

    from ...schemas.recommendation import ExplanationOut

    payload = _serializable(value)
    if isinstance(payload, dict) and isinstance(payload.get("items"), dict):
        payload = payload["items"]
    if not isinstance(payload, dict):
        return {}
    out: dict[str, Any] = {}
    for key, item in payload.items():
        if not isinstance(item, dict):
            continue
        fields = {name: item.get(name) or [] for name in ExplanationOut.model_fields}
        out[str(key)] = ExplanationOut(**fields)
    return out


def _explanation_text(houses: list[dict[str, Any]], explanation: Any) -> str:
    items = explanation.get("items") if isinstance(explanation, dict) else getattr(explanation, "items", None)
    lines: list[str] = []
    if isinstance(items, dict):
        for house in houses:
            item = items.get(house.get("id"))
            if not item:
                continue
            why = item.get("why") if isinstance(item, dict) else getattr(item, "why", [])
            if why:
                lines.append(f"{house.get('no')} {house.get('name')}：" + "；".join(why[:2]))
    return "\n".join(lines)


def _chunks(text: str, size: int):
    for index in range(0, len(text), size):
        yield text[index : index + size]


def _hard_rule_lines(prefs: dict[str, Any]) -> list[str]:
    return [
        f"预算上限：{prefs.get('budget')} 元/月（超出直接淘汰）" if prefs.get("budget") else "预算：未设置",
        f"通勤上限：{prefs.get('commute')} 分钟（超出直接淘汰）" if prefs.get("commute") else "通勤：未设置",
        "必须独立卫浴" if prefs.get("need_bathroom") else "独立卫浴：非硬约束",
        "允许合租" if prefs.get("allow_shared") else "不接受合租",
    ]


def _soft_rule_lines(prefs: dict[str, Any]) -> list[str]:
    soft = prefs.get("soft") or {}
    labels = {
        "south": "南向",
        "light": "采光好",
        "high_floor": "中高楼层",
        "big_area": "面积大",
        "flex_pay": "付款灵活",
    }
    chosen = [label for key, label in labels.items() if soft.get(key)]
    return chosen or ["未设置软偏好（仅按硬约束与成本排序）"]


def build_about(prefs: Mapping[str, Any], houses: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """硬约束/软偏好/比较窗口/缺失字段说明。GET 时用快照重算，保证报告与快照一致。"""

    rows = list(houses)
    return {
        "hard_rules": _hard_rule_lines(dict(prefs)),
        "soft_rules": _soft_rule_lines(dict(prefs)),
        "window": engine.check_compare_window(rows),
        "missing": [
            f"{house.get('no')}：{'、'.join(engine.missing_fields(house))}"
            for house in rows
            if engine.missing_fields(house)
        ],
    }


async def workspace_exists(db, workspace_id: str) -> Workspace | None:
    return await db.get(Workspace, workspace_id)
