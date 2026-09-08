import asyncio
import json
from collections.abc import AsyncIterator

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Clause, Contract, ContractStatus, Risk, RiskLevel
from .extract import ExtractError, extract_clauses, grounding_ok
from .rules import RULES, health_score, negotiation_script


def _ev(event: str, data: dict) -> dict:
    return {"event": event, "data": json.dumps(data, ensure_ascii=False)}


def _progress(index: int, label: str, status: str) -> dict:
    return _ev("progress", {"index": index, "label": label, "status": status})


class _Failed(Exception):
    """可预期的分析失败：带 code 透传给前端（区别于未预期的 500 式异常）"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


async def run_analysis(db: AsyncSession, contract_id: int) -> AsyncIterator[dict]:
    contract = await db.get(Contract, contract_id)
    if contract is None:
        yield _ev("error", {"code": "NOT_FOUND", "message": "合同不存在"})
        return

    text = contract.raw_text
    try:
        contract.status = ContractStatus.analyzing
        await db.commit()

        label0 = f"解析文档（{len(text)} 字符）"
        yield _progress(0, label0, "active")
        await asyncio.sleep(0.5)
        yield _progress(0, label0, "done")

        yield _progress(1, "抽取条款", "active")
        try:
            extracted = await extract_clauses(text)
        except ExtractError as exc:
            raise _Failed(exc.code, exc.message) from exc
        clause_data = grounding_ok(extracted, text)
        dropped = len(extracted) - len(clause_data)
        if not clause_data:
            raise _Failed(
                "NO_CLAUSES",
                "未识别到任何条款（文本可能缺少「第 N 条」结构或不是合同正文），请粘贴完整合同文本后重试",
            )
        await db.execute(delete(Risk).where(Risk.contract_id == contract_id))
        await db.execute(delete(Clause).where(Clause.contract_id == contract_id))
        rows = [
            Clause(
                contract_id=contract_id,
                clause_no=c.clause_no,
                clause_type=c.clause_type,
                title=c.title,
                raw_text=c.raw_text,
                amount=c.amount,
                months=c.months,
                party_liable=c.party_liable,
            )
            for c in clause_data
        ]
        db.add_all(rows)
        await db.flush()
        label1 = f"抽取 {len(rows)} 项条款" + (f"（{dropped} 项因无法定位原文被丢弃）" if dropped else "")
        yield _progress(1, label1, "done")

        rules_label = f"匹配风险规则库（{len(RULES)} 条规则）"
        yield _progress(2, rules_label, "active")
        risks: list[Risk] = []
        hits = []
        for data, row in zip(clause_data, rows, strict=True):
            for rule in RULES:
                hit = rule(data)
                if hit:
                    hits.append(hit)
                    risks.append(
                        Risk(
                            contract_id=contract_id,
                            clause_id=row.id,
                            level=RiskLevel(hit.level),
                            rule_id=hit.rule_id,
                            title=hit.title,
                            reason=hit.reason,
                            suggestion=hit.suggestion,
                            negotiation_script=negotiation_script(hit, row.clause_no, row.title),
                        )
                    )
        score = health_score(hits)
        contract.health_score = score
        contract.status = ContractStatus.done
        contract.error = None
        db.add_all(risks)
        await db.commit()
        yield _progress(2, f"{rules_label} · 命中 {len(risks)} 项", "done")

        yield _ev("done", {"contract_id": contract_id, "clause_count": len(rows), "risk_count": len(risks), "health_score": score})
    except _Failed as exc:
        contract.status = ContractStatus.failed
        contract.error = str(exc)
        await db.commit()
        yield _ev("error", {"code": exc.code, "message": str(exc)})
    except Exception as exc:
        contract.status = ContractStatus.failed
        contract.error = str(exc)
        await db.commit()
        yield _ev("error", {"code": "ANALYZE_FAILED", "message": f"分析中断：{type(exc).__name__}: {exc}"})
