"""流程 B：房源承诺 × 合同条款核验（PRD §3.3、场景 2）。

两段合并：
1. 确定性比较（金额/日期/枚举/承担方）→ `services/verify_rules.py`；
2. 语义判断（维修责任、口头承诺、模糊表述）→ `services/llm/verify.py`，且必须引用已有条款或输出「未约定」。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, select

from ...db import SessionLocal
from ...errors import AppError
from ...models import Clause, Contract, House, Verification, VerificationItem
from .. import engine
from ..convert import house_to_dict, verification_out
from ..runs import RunContext

RESULT_ORDER = {"冲突": 0, "未约定": 1, "无法判断": 2, "一致": 3}

# 房源详情抽屉的定位锚点（HouseDrawer 用 data-anchor 滚动到字段）
ANCHORS = {
    "租金": "hd-rent",
    "押金与付款方式": "hd-deposit",
    "押金/付款方式": "hd-deposit",
    "押金方式": "hd-deposit",
    "押金": "hd-deposit",
    "物业费": "hd-property",
    "宠物": "hd-pet",
    "可入住时间": "hd-available",
    "起租日期": "hd-available",
}


async def run_verification(run: RunContext, verification_id: str) -> dict[str, Any]:
    async with SessionLocal() as db:
        verification = await db.get(Verification, verification_id)
        if verification is None:
            raise AppError("NOT_FOUND", "核验任务不存在")
        house = await db.get(House, verification.house_id)
        contract = await db.get(Contract, verification.contract_id)
        if house is None or contract is None:
            raise AppError("CONTEXT_MISSING", "核验所需的房源或合同已被删除")

        clauses = list(
            (
                await db.execute(
                    select(Clause).where(Clause.contract_id == contract.id).order_by(Clause.clause_no)
                )
            ).scalars()
        )
        if not clauses:
            raise AppError("NO_CLAUSES", "该合同还没有解析出条款", "请先完成合同解析（重新解析）")

        await run.progress("verify", 0, "读取房源承诺与合同条款", "active")
        house_data = house_to_dict(house)
        clause_dicts = [_clause_dict(clause) for clause in clauses]
        await run.progress("verify", 0, f"房源 1 套 · 条款 {len(clause_dicts)} 项", "done")

        run.check_cancelled()
        await run.progress("verify", 1, "逐项比对（金额 / 日期 / 承担方）", "active")
        rows: list[Any] = list(engine.compare_claims(house_data, clause_dicts))
        _normalise_rows(rows, clause_dicts)

        promises = [note for note in (house_data.get("verify") or []) if isinstance(note, str) and note.strip()]
        semantic_notes = [
            (value, label)
            for value, label in (
                (house_data.get("furniture"), "家具家电"),
                (house_data.get("lighting"), "采光"),
                (house_data.get("nearby"), "周边配套"),
                (house_data.get("lease_req"), "租期要求"),
            )
            if value
        ]
        for promise in promises:
            run.check_cancelled()
            judgement = await engine.judge_promise(promise, "口头承诺", clause_dicts)
            rows.append(_promise_row(promise, judgement, clause_dicts))
        for value, label in semantic_notes:
            run.check_cancelled()
            judgement = await engine.judge_promise(str(value), label, clause_dicts)
            rows.append(_promise_row(str(value), judgement, clause_dicts))

        rows.sort(key=lambda row: (RESULT_ORDER.get(getattr(row, "result", "无法判断"), 9), getattr(row, "field", "")))
        await run.progress("verify", 1, f"比对完成：{_summary_text(rows)}", "done")

        await db.execute(delete(VerificationItem).where(VerificationItem.verification_id == verification.id))
        await db.flush()
        for row in rows:
            clause_ref = _resolve_clause(clause_dicts, getattr(row, "clause_id", None))
            clause_no = (clause_ref or {}).get("clause_no")
            db.add(
                VerificationItem(
                    verification_id=verification.id,
                    claim=getattr(row, "claim", ""),
                    field=getattr(row, "field", ""),
                    anchor=ANCHORS.get(getattr(row, "field", "")),
                    clause_id=(clause_ref or {}).get("id"),
                    clause_no=clause_no,
                    clause_text=_clause_text(clause_ref, row),
                    page=(clause_ref or {}).get("page") if clause_ref else None,
                    char_start=(clause_ref or {}).get("char_start") if clause_ref else None,
                    char_end=(clause_ref or {}).get("char_end") if clause_ref else None,
                    result=getattr(row, "result", "无法判断"),
                    advice=getattr(row, "advice", ""),
                    severity=getattr(row, "severity", None),
                    reason=getattr(row, "reason", ""),
                )
            )
        verification.summary = _summary(rows)
        verification.negotiation = _negotiation(rows)
        verification.status = "done"
        verification.error = None
        await db.commit()
        await db.refresh(verification, attribute_names=["items"])
        return verification_out(verification).model_dump(mode="json")


def _clause_text(clause_ref: dict[str, Any] | None, row: Any) -> str:
    if clause_ref is not None:
        return str(clause_ref.get("raw_text") or "")
    return str(getattr(row, "clause_text", "") or "")


def _clause_dict(clause: Clause) -> dict[str, Any]:
    return {
        "id": clause.id,
        "clause_no": clause.clause_no,
        "clause_type": clause.clause_type,
        "title": clause.title,
        "raw_text": clause.raw_text,
        "text": clause.raw_text,
        "page": clause.page,
        "char_start": clause.char_start,
        "char_end": clause.char_end,
    }


def _clause_lookup(clauses: list[dict[str, Any]], clause_no: int | None) -> dict[str, Any] | None:
    if clause_no is None:
        return None
    for clause in clauses:
        if clause.get("clause_no") == clause_no:
            return clause
    return None


def _clause_by_id(clauses: list[dict[str, Any]], clause_id: Any) -> dict[str, Any] | None:
    if clause_id is None:
        return None
    for clause in clauses:
        if clause.get("id") == clause_id:
            return clause
    return None


def _resolve_clause(clauses: list[dict[str, Any]], ref: Any) -> dict[str, Any] | None:
    """确定性规则里的 `clause_id` 是条号；LLM 判断行可能是条号也可能是条款 id，两种都试。"""

    if ref is None:
        return None
    match = _clause_lookup(clauses, ref if isinstance(ref, int) else None)
    return match or _clause_by_id(clauses, ref)


def _normalise_rows(rows: list[Any], clauses: list[dict[str, Any]]) -> None:
    """确定性规则返回的 VRow 只有 clause_id：把 clause_no 补上（LLM 判断行已带 clause_no）。"""

    for row in rows:
        if not hasattr(row, "clause_id"):
            continue
        clause = _resolve_clause(clauses, row.clause_id)
        if clause is not None:
            row.clause_no = clause.get("clause_no")
        elif getattr(row, "result", "") == "一致":
            # 规则说一致却没有条款引用，判不了：降级为无法判断，避免假结论
            row.result = "无法判断"


class _Row:
    """把 LLM 判断结果适配成与 verify_rules.VRow 相同的形状。"""

    def __init__(
        self,
        *,
        claim: str,
        field: str,
        result: str,
        advice: str,
        severity: str | None,
        clause_no: int | None,
        reason: str,
    ) -> None:
        self.claim = claim
        self.field = field
        self.anchor = None
        self.result = result
        self.advice = advice
        self.severity = severity
        self.clause_no = clause_no
        self.reason = reason


def _promise_row(promise: str, judgement: Any, clauses: list[dict[str, Any]]) -> _Row:
    result = getattr(judgement, "result", "未约定")
    clause_no = getattr(judgement, "clause_no", None)
    if clause_no is not None and _clause_lookup(clauses, clause_no) is None:
        result, clause_no = "未约定", None
    return _Row(
        claim=promise,
        field="承诺",
        result=result,
        advice=getattr(judgement, "advice", ""),
        severity=getattr(judgement, "severity", None),
        clause_no=clause_no,
        reason=getattr(judgement, "reason", ""),
    )


def _summary(rows: list[Any]) -> dict[str, Any]:
    counts = {"一致": 0, "冲突": 0, "未约定": 0, "无法判断": 0}
    high: list[str] = []
    for row in rows:
        result = getattr(row, "result", "无法判断")
        counts[result] = counts.get(result, 0) + 1
        if result == "冲突" and getattr(row, "severity", None) == "high":
            high.append(getattr(row, "field", ""))
    return {**counts, "high_priority": high, "total": len(rows)}


def _summary_text(rows: list[Any]) -> str:
    summary = _summary(rows)
    return " · ".join(
        [
            f"一致 {summary['一致']}",
            f"冲突 {summary['冲突']}",
            f"未约定 {summary['未约定']}",
            f"无法判断 {summary['无法判断']}",
        ]
    )


def _negotiation(rows: list[Any]) -> str:
    conflicts = [row for row in rows if getattr(row, "result", "") == "冲突"]
    if not conflicts:
        return ""
    lines: list[str] = []
    for index, row in enumerate(conflicts, start=1):
        clause_no = getattr(row, "clause_no", None)
        ref = f"第 {clause_no} 条" if clause_no else "对应条款"
        lines.append(
            f"{index}. {ref}（{getattr(row, 'field', '')}）：合同写的是你确认的房源承诺之外的内容，"
            f"建议按「{getattr(row, 'claim', '')}」修改；{getattr(row, 'advice', '')}"
        )
    return "建议与房东确认并修改的条款（可直接发给房东）：\n" + "\n".join(lines)
