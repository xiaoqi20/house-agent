"""ORM ↔ API 模型转换。

前端的 House/Contract 字段就是产品口径（web/src/types.ts），这里保持一一对应，
并把「信息完整度 / 缺失字段 / 来源标签 / 证据」在读取时统一算好（不让前端各算一套）。
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from sqlalchemy import inspect

from ..models import Clause, Contract, House, HouseEvidence, Verification, VerificationItem
from ..schemas.chat import MessageOut
from ..schemas.contract import ClauseRisk, ClauseView, ContractOut
from ..schemas.house import HouseOut
from ..schemas.verification import VerificationItemOut, VerificationOut
from ..services import domain

# ORM 字段 → 前端 House 字段（用于 domain 的 camelCase 归一化）
HOUSE_FIELDS: tuple[str, ...] = (
    "name",
    "region",
    "address",
    "rent",
    "deposit",
    "agency_fee",
    "property_fee",
    "property_bear",
    "net_fee",
    "other_fee",
    "area",
    "layout",
    "floor",
    "orientation",
    "bathroom",
    "lighting",
    "furniture",
    "commute_min",
    "commute_mode",
    "metro",
    "nearby",
    "pet",
    "shared",
    "sublet",
    "max_people",
    "lease_req",
    "available",
    "notes",
    "link_url",
)


def loaded(obj: object, name: str, default):
    """安全读取 ORM 关系：未预加载时返回默认值，避免异步上下文外触发懒加载（MissingGreenlet）。"""

    state = inspect(obj)
    if state is not None and name in state.unloaded:
        return default
    return getattr(obj, name, default)


def house_to_dict(house: House | Mapping[str, Any]) -> dict[str, Any]:
    """房源 → 纯 dict（供 domain / verify_rules / LLM 使用，字段名用前端 camelCase）。"""

    if isinstance(house, Mapping):
        raw = dict(house)
    else:
        raw = {field: getattr(house, field) for field in ("id", "no", *HOUSE_FIELDS)}
        raw["status"] = house.status
        raw["source"] = house.source
        raw["raw"] = house.raw
        raw["verify"] = list(house.verify or [])
        raw["todos"] = list(house.todos or [])
        raw["visits"] = list(house.visits or [])
        raw["contract_id"] = house.contract_id
    return domain.normalise_house(raw)


def house_out(house: House, evidence: Iterable[HouseEvidence] | None = None) -> HouseOut:
    """房源 → API 模型。

    字段值直接取 ORM 行（API 契约就是「库里存了什么就返回什么」），
    完整度/缺失字段用 domain 口径现算（domain 只覆盖参与比较的字段，不做完整字段清单）。
    """

    raw = house_to_dict(house)
    columns = {
        name
        for name in HouseOut.model_fields
        if name not in {"source_label", "completeness", "missing", "evidence"}
    }
    data = {name: getattr(house, name, None) for name in columns}
    for name, field in HouseOut.model_fields.items():
        if name in data and data[name] is None and field.annotation is str:
            data[name] = ""
    if data.get("shared") is None:
        data["shared"] = False
    rows = evidence if evidence is not None else loaded(house, "evidence", [])
    data.update(
        {
            "source_label": domain.SOURCE_LABEL.get(house.source, house.source),
            "completeness": domain.completeness(raw),
            "missing": domain.missing_fields(raw),
            "evidence": {item.field: item.snippet for item in rows},
            "visits": list(house.visits or []),
            "todos": list(house.todos or []),
            "verify": list(house.verify or []),
        }
    )
    return HouseOut(**data)


def clause_view(clause: Clause) -> ClauseView:
    risks = [
        ClauseRisk(
            id=risk.id,
            level=risk.level,
            rule_id=risk.rule_id,
            title=risk.title,
            reason=risk.reason,
            suggestion=risk.suggestion,
            negotiation_script=risk.negotiation_script,
        )
        for risk in loaded(clause, "risks", [])
    ]
    return ClauseView(
        id=clause.id,
        clause_no=clause.clause_no,
        clause_type=clause.clause_type,
        title=clause.title,
        raw_text=clause.raw_text,
        page=clause.page,
        char_start=clause.char_start,
        char_end=clause.char_end,
        is_risk=bool(risks),
        risks=risks,
    )


def _risk_dict(risk) -> dict[str, Any]:
    return {
        "id": risk.id,
        "level": risk.level,
        "clause_id": risk.clause_id,
        "clause_no": getattr(loaded(risk, "clause", None), "clause_no", None),
        "clause_title": getattr(loaded(risk, "clause", None), "title", None),
        "rule_id": risk.rule_id,
        "title": risk.title,
        "reason": risk.reason,
        "suggestion": risk.suggestion,
        "negotiation_script": risk.negotiation_script,
    }


def contract_out(contract: Contract) -> ContractOut:
    clauses = sorted(loaded(contract, "clauses", []), key=lambda c: (c.clause_no is None, c.clause_no or 0))
    risk_clauses: list[int] = []
    for clause in clauses:
        if loaded(clause, "risks", []) and clause.clause_no is not None and clause.clause_no not in risk_clauses:
            risk_clauses.append(clause.clause_no)
    return ContractOut(
        id=contract.id,
        no=contract.no,
        name=contract.name or contract.filename or "合同",
        source=contract.source_type,
        time=(contract.created_at.date().isoformat() if contract.created_at else ""),
        status=contract.status if isinstance(contract.status, str) else contract.status.value,
        reason=contract.error or "",
        size=contract.size_label,
        bound_house_id=contract.house_id,
        clauses_list=[
            (clause.clause_no, clause.title or clause.clause_type, clause.raw_text) for clause in clauses
        ],
        risk_clauses=risk_clauses,
        negotiation=contract.negotiation or "",
        health_score=contract.health_score,
        page_count=contract.page_count,
        created_at=contract.created_at,
    )


def verification_item_out(item: VerificationItem) -> VerificationItemOut:
    return VerificationItemOut(
        id=item.id,
        claim=item.claim,
        field=item.field,
        anchor=item.anchor,
        clause_id=item.clause_id,
        clause_no=item.clause_no,
        clause_text=item.clause_text,
        page=item.page,
        char_start=item.char_start,
        char_end=item.char_end,
        result=item.result,
        advice=item.advice,
        severity=item.severity,
        reason=item.reason,
    )


def verification_out(verification: Verification) -> VerificationOut:
    return VerificationOut(
        id=verification.id,
        house_id=verification.house_id,
        contract_id=verification.contract_id,
        status=verification.status,
        summary=dict(verification.summary or {}),
        items=[verification_item_out(item) for item in loaded(verification, "items", [])],
        negotiation=verification.negotiation or "",
        error=verification.error,
        created_at=verification.created_at,
        run_id=verification.run_id,
    )


def message_out(message) -> MessageOut:
    return MessageOut(
        id=message.id,
        role=message.role,
        content=dict(message.content or {}),
        citations=list(message.citations or []),
        created_at=message.created_at,
    )
