"""对外唯一入口门面（facade）：把 W1 的解析层 / 领域层 / LLM 层收敛成稳定接口。

路由与工作流只依赖这里；各层内部实现替换（mock ↔ 真实模型、正则 ↔ 规则）不影响调用方。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from . import domain as _domain
from . import verify_rules as _verify_rules
from .llm import answer as _llm_answer
from .llm import contracts as _llm_contracts
from .llm import explain as _llm_explain
from .llm import listing as _llm_listing
from .llm import verify as _llm_verify
from .parsing import (
    SUPPORTED_EXTENSIONS,
    EmptyDocument,
    NoTextLayer,
    ParsedDoc,
    ParseError,
    UnsupportedFormat,
    parse_document,
    parse_text,
    rows_to_text,
)

# ==================== 解析层 ====================

ParseError = ParseError
UnsupportedFormat = UnsupportedFormat
NoTextLayer = NoTextLayer
EmptyDocument = EmptyDocument
ParsedDoc = ParsedDoc
SUPPORTED_EXTENSIONS = SUPPORTED_EXTENSIONS
parse_document = parse_document
parse_text = parse_text
rows_to_text = rows_to_text


# ==================== 领域层（确定性：不得由 LLM 计算） ====================


def normalise_house(house: Mapping[str, Any]) -> dict[str, Any]:
    return _domain.normalise_house(house)


# 兼容两种拼写（调用方有美式习惯）
normalize_house = normalise_house


def normalise_prefs(prefs: Mapping[str, Any]) -> Any:
    return _domain.normalise_prefs(prefs)


def completeness(house: Mapping[str, Any]) -> int:
    return _domain.completeness(house)


def missing_fields(house: Mapping[str, Any]) -> list[str]:
    return _domain.missing_fields(house)


def monthly_cost(house: Mapping[str, Any]) -> dict[str, Any]:
    return _domain.monthly_cost(house)


def one_time_cost(house: Mapping[str, Any]) -> dict[str, Any]:
    return _domain.one_time_cost(house)


def hard_violations(house: Mapping[str, Any], prefs: Mapping[str, Any]) -> list[str]:
    return _domain.hard_violations(house, prefs)


def soft_score(house: Mapping[str, Any], prefs: Mapping[str, Any]) -> dict[str, Any]:
    return _domain.soft_score(house, prefs)


def comparison_missing_fields(house: Mapping[str, Any], prefs: Mapping[str, Any]) -> list[str]:
    return _domain.comparison_missing_fields(house, prefs)


def rank_views(houses: Sequence[Mapping[str, Any]], prefs: Mapping[str, Any]) -> dict[str, list[Any]]:
    """返回 {"budget": [RankItem...], "commute": [...], "mix": [...]}（三套确定性排序，PRD §8）。"""

    return {view: _domain.rank_views(houses, prefs, view) for view in ("budget", "commute", "mix")}


def check_compare_window(houses: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return _domain.check_compare_window(houses)


def verdict(*args: Any, **kwargs: Any) -> str:
    return _domain.verdict(*args, **kwargs)


SOURCE_LABEL: dict[str, str] = _domain.SOURCE_LABEL


# ==================== 核验规则（确定性部分） ====================


def compare_claims(house: Mapping[str, Any], clauses: Sequence[Mapping[str, Any]]) -> list[Any]:
    return _verify_rules.compare_claims(house, clauses)


# ==================== LLM 层 ====================


async def extract_listings(text: str, source: str = "paste") -> Any:
    return await _llm_listing.extract_listings(text, source)


async def extract_clauses(text: str, pages: list[str] | None = None) -> Any:
    return await _llm_contracts.extract_clauses(text, pages)


def as_clause_data(clauses: Sequence[Any]) -> list[Any]:
    """把 dict / ORM 条款统一成 LLM 层的 ClauseData（LLM 层只认契约模型）。"""

    from .llm.models import ClauseData

    out: list[Any] = []
    for item in clauses:
        if isinstance(item, ClauseData):
            out.append(item)
            continue
        if isinstance(item, Mapping):
            getter = item.get
        else:

            def getter(key, default=None, item=item):
                return getattr(item, key, default)

        text = getter("text") or getter("raw_text") or ""
        out.append(
            ClauseData(
                clause_no=getter("clause_no"),
                title=getter("title") or getter("clause_type") or "",
                text=text,
                clause_type=getter("clause_type") or "其他",
                page=getter("page"),
                char_start=getter("char_start"),
                char_end=getter("char_end"),
                amount=getter("amount"),
                months=getter("months"),
                party_liable=getter("party_liable"),
            )
        )
    return out


async def judge_promise(claim: str, field: str, clauses: Sequence[Any]) -> Any:
    return await _llm_verify.judge_promise(claim, field, as_clause_data(clauses))


def stream_answer(
    question: str,
    house: Mapping[str, Any] | None,
    clauses: Sequence[Any],
    contract_id: str | None,
    sink: dict[str, Any],
) -> Any:
    """真流式问答：异步产出已净化的 HTML 片段，终结结果写入 sink["result"]。"""

    return _llm_answer.stream_answer(question, house, as_clause_data(clauses), contract_id, sink)


async def answer_question(
    question: str,
    house: Mapping[str, Any] | None,
    clauses: Sequence[Any],
    contract_id: str | None,
) -> Any:
    return await _llm_answer.answer_question(question, house, as_clause_data(clauses), contract_id)


async def explain_recommendation(
    houses: Sequence[Mapping[str, Any]], prefs: Mapping[str, Any], ranking: Sequence[Any]
) -> Any:
    """排名列表 → {house_id: 该房源的排序结果}（LLM 层按 house_id 取用）。"""

    from dataclasses import asdict, is_dataclass

    items: dict[str, Any] = {}
    for item in ranking:
        if isinstance(item, Mapping):
            data = dict(item)
        elif is_dataclass(item) and not isinstance(item, type):
            data = asdict(item)
        else:
            data = {key: getattr(item, key) for key in dir(item) if not key.startswith("_")}
        house_id = str(data.get("house_id") or "")
        if house_id:
            items[house_id] = data
    return await _llm_explain.explain_recommendation(houses, prefs, items)
