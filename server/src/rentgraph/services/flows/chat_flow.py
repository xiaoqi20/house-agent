"""流程 C：上下文问答（PRD §5 流程 C）。

只装载当前 `house_id` 与可选 `contract_id`；引用必须存在，否则降级为通用建议。
回答先整段校验（引用/降级/免责），再按块推 token，前端只负责渲染。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from ...db import SessionLocal
from ...errors import AppError
from ...models import Clause, Contract, Conversation, House, Message
from .. import engine
from ..convert import house_to_dict
from ..runs import RunContext


async def run_answer(run: RunContext, conversation_id: str, user_message_id: str, text: str) -> dict[str, Any]:
    async with SessionLocal() as db:
        conversation = await db.get(Conversation, conversation_id)
        if conversation is None:
            raise AppError("NOT_FOUND", "对话不存在")
        user_message = await db.get(Message, user_message_id)
        if user_message is None:
            raise AppError("NOT_FOUND", "消息不存在")

        house_id = run.house_id
        contract_id = run.contract_id
        house = await db.get(House, house_id) if house_id else None
        contract = await db.get(Contract, contract_id) if contract_id else None
        clauses: list[Clause] = []
        if contract is not None:
            clauses = list(
                (
                    await db.execute(
                        select(Clause).where(Clause.contract_id == contract.id).order_by(Clause.clause_no)
                    )
                ).scalars()
            )

        await run.progress("answer", 0, "检索当前上下文", "active")
        context_parts = []
        if house is not None:
            context_parts.append(f"房源 {house.no}")
        if contract is not None:
            context_parts.append(f"合同 {len(clauses)} 项条款")
        context_label = "、".join(context_parts) if context_parts else "无（通用建议）"
        await run.progress("answer", 0, f"上下文：{context_label}", "done")

        run.check_cancelled()
        await run.progress("answer", 1, "生成回答并校验引用", "active")
        # 真流式：模型逐段产出 → 逐段推 token（用户看到的就是模型输出速度）；引用/模式在结尾校验后落库
        sink: dict[str, Any] = {}
        stream = engine.stream_answer(
            text,
            house_to_dict(house) if house is not None else None,
            [_clause_payload(clause) for clause in clauses],
            contract.id if contract is not None else None,
            sink,
        )
        async for delta in stream:
            run.check_cancelled()
            await run.token(delta)
        answer = sink.get("result")
        if answer is None:
            raise AppError("ANALYZE_FAILED", "回答生成失败", "请重试或换个问法")
        html = getattr(answer, "html", "") or ""
        citations = [citation.model_dump() for citation in getattr(answer, "citations", []) or []]
        citations = _validate_citations(citations, clauses)
        mode = getattr(answer, "mode", "general")
        if not citations and mode == "context":
            mode = "house_only" if house is not None else "general"

        await run.progress("answer", 1, "回答完成", "done")

        ai_message = Message(
            conversation_id=conversation.id,
            role="ai",
            content={
                "mode": mode,
                "html": html,
                "followups": list(getattr(answer, "followups", []) or []),
                "sources": list(getattr(answer, "sources", []) or []),
            },
            citations=citations,
        )
        db.add(ai_message)
        await db.commit()
        await db.refresh(ai_message)

        from ...schemas.chat import AnswerOut, CitationOut

        payload = AnswerOut(
            message_id=ai_message.id,
            mode=mode,
            html=html,
            citations=[CitationOut(**citation) for citation in citations],
            followups=list(getattr(answer, "followups", []) or []),
            sources=list(getattr(answer, "sources", []) or []),
        )
        return payload.model_dump(mode="json")


def _clause_payload(clause: Clause) -> dict[str, Any]:
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


def _validate_citations(citations: list[dict[str, Any]], clauses: list[Clause]) -> list[dict[str, Any]]:
    """引用存在性校验：不存在的条款号一律剔除（不得声称「根据你的合同」）。"""

    by_no = {clause.clause_no: clause for clause in clauses if clause.clause_no is not None}
    by_id = {clause.id: clause for clause in clauses}
    out: list[dict[str, Any]] = []
    for citation in citations:
        clause = by_id.get(citation.get("clause_id")) or by_no.get(citation.get("clause_no"))
        if clause is None:
            continue
        citation = {
            **citation,
            "clause_id": clause.id,
            "clause_no": clause.clause_no,
            "label": citation.get("label") or f"第 {clause.clause_no} 条",
            "page": clause.page,
            "char_start": clause.char_start,
            "char_end": clause.char_end,
        }
        if citation not in out:
            out.append(citation)
    return out


def _chunks(text: str, size: int):
    for index in range(0, len(text), size):
        yield text[index : index + size]
