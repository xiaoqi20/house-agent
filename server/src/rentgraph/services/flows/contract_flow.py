"""流程：合同解析 → 条款抽取（带页码/字符区间）→ 一期规则库风险扫描。

复用一期合同风险雷达的资产：`services/rules.py`（10 条声明式规则）与 `services/extract.py`
的抽取契约；v1.1 增加 workspace/house 绑定与原文定位字段。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete

from ...db import SessionLocal
from ...errors import AppError
from ...models import Clause, Contract, Risk
from ...schemas.extraction import ClauseData
from .. import engine
from ..rules import RULES, health_score, negotiation_script
from ..runs import RunContext
from ..storage import storage

MIN_CONTRACT_CHARS = 200
OCR_SOURCES = {"image", "png", "jpg", "jpeg", "webp"}


async def run_contract_analysis(run: RunContext, contract_id: str) -> dict[str, Any]:
    async with SessionLocal() as db:
        contract = await db.get(Contract, contract_id)
        if contract is None:
            raise AppError("NOT_FOUND", "合同不存在或已被删除")

        if contract.source_type in OCR_SOURCES:
            contract.status = "failed"
            contract.error = "图片/扫描件暂不支持 OCR（一期规划能力），请粘贴合同文本"
            await db.commit()
            raise AppError("OCR_UNSUPPORTED", contract.error, "请用 PDF 文字版、Word 或直接粘贴文本")

        contract.status = "parsing"
        await db.commit()

        try:
            await run.progress("parse", 0, "解析文档", "active")
            pages: list[str] = []
            if contract.storage_key:
                data = storage.read(contract.storage_key)
                doc = engine.parse_document(contract.filename or "contract.pdf", data)
                pages = [page.text for page in doc.pages]
                contract.raw_text = doc.text
                contract.page_count = doc.page_count or (1 if doc.text else 0)
            else:
                doc = engine.parse_text(contract.raw_text or "")
                contract.page_count = 1
            text = (doc.text or "").strip()
            if len(text) < MIN_CONTRACT_CHARS:
                raise AppError(
                    "TEXT_TOO_SHORT",
                    f"仅解析到 {len(text)} 字，低于合同最小长度 {MIN_CONTRACT_CHARS} 字",
                    "请粘贴完整的合同正文（含「第 N 条」结构）后重试",
                )
            await run.progress("parse", 0, "解析文档", "done", f"{len(text)} 字 · {contract.page_count} 页")

            run.check_cancelled()
            contract.status = "analyzing"
            await db.commit()

            await run.progress("extract", 1, "抽取条款（含原文定位）", "active")
            extraction = await engine.extract_clauses(text, pages or None)
            dropped = int(getattr(extraction, "dropped", 0) or 0)
            clause_data: list[ClauseData] = list(extraction.clauses)
            if not clause_data:
                raise AppError(
                    "NO_CLAUSES",
                    "未识别到任何条款（文本可能缺少「第 N 条」结构或不是合同正文）",
                    "请粘贴完整合同文本后重试",
                )
            label = f"清单 {len(clause_data)} 项条款"
            if dropped:
                label += f"（{dropped} 项因无法定位原文被丢弃）"
            await run.progress("extract", 1, label, "done")

            # 幂等：重新分析先清空旧条款/风险
            await db.execute(delete(Risk).where(Risk.contract_id == contract.id))
            await db.execute(delete(Clause).where(Clause.contract_id == contract.id))
            await db.flush()

            rows: list[Clause] = []
            for data in clause_data:
                row = Clause(
                    contract_id=contract.id,
                    clause_no=data.clause_no,
                    clause_type=data.clause_type or "其他",
                    title=data.title or "",
                    raw_text=data.text,
                    page=data.page,
                    char_start=data.char_start,
                    char_end=data.char_end,
                    amount=data.amount,
                    months=data.months,
                    party_liable=data.party_liable,
                )
                db.add(row)
                rows.append(row)
            await db.flush()

            run.check_cancelled()
            await run.progress("rules", 2, "匹配风险规则库", "active")
            hit_pairs: list[tuple[Clause, Any]] = []
            for row in rows:
                probe = ClauseData(
                    clause_no=row.clause_no,
                    clause_type=row.clause_type,
                    title=row.title,
                    raw_text=row.raw_text,
                    amount=row.amount,
                    months=row.months,
                    party_liable=row.party_liable,
                )
                for check in RULES:
                    hit = check(probe)
                    if hit is None:
                        continue
                    hit_pairs.append((row, hit))
                    db.add(
                        Risk(
                            contract_id=contract.id,
                            clause_id=row.id,
                            level=hit.level,
                            rule_id=hit.rule_id,
                            title=hit.title,
                            reason=hit.reason,
                            suggestion=hit.suggestion,
                            negotiation_script=negotiation_script(hit, row.clause_no, row.title),
                        )
                    )
            contract.health_score = health_score([hit for _, hit in hit_pairs])
            contract.negotiation = _negotiation(hit_pairs)
            contract.status = "done"
            contract.error = None
            if not contract.name:
                contract.name = contract.filename or "粘贴的合同文本"
            await db.commit()
            await run.progress("rules", 2, f"命中 {len(hit_pairs)} 项风险", "done")

            await db.refresh(contract, attribute_names=["clauses", "risks"])
            from ..convert import contract_out

            return contract_out(contract).model_dump(mode="json")
        except AppError as exc:
            contract.status = "failed"
            contract.error = exc.message
            await db.commit()
            raise
        except Exception as exc:  # noqa: BLE001 - 记录并转为统一错误事件
            code = getattr(exc, "code", None)
            message = getattr(exc, "message", None)
            hint = getattr(exc, "hint", None)
            contract.status = "failed"
            if isinstance(code, str) and isinstance(message, str):
                # 解析层的明确错误（NO_TEXT_LAYER / UNSUPPORTED_FORMAT / EMPTY_DOCUMENT …）原样上抛：
                # 前端要靠 code 决定引导文案（例如扫描件 → 提示粘贴文本）
                contract.error = message
                await db.commit()
                raise AppError(code, message, hint or "") from exc
            contract.error = f"解析中断：{type(exc).__name__}"
            await db.commit()
            raise AppError("ANALYZE_FAILED", contract.error, "可点「重新解析」重试") from exc


def _negotiation(hit_pairs: list[tuple[Clause, Any]]) -> str:
    """逐条话术汇总（可整段复制给房东），条号来自实际命中的条款。"""

    if not hit_pairs:
        return ""
    lines: list[str] = []
    seen: set[tuple[int | None, str]] = set()
    for index, (row, hit) in enumerate(hit_pairs, start=1):
        key = (row.clause_no, hit.rule_id)
        if key in seen:
            continue
        seen.add(key)
        ref = f"第 {row.clause_no} 条" if row.clause_no else "相关条款"
        ask = hit.ask or hit.suggestion
        lines.append(f"{index}. {ref}（{row.title or row.clause_type}）：{hit.reason}。建议改为「{ask}」。")
    return "建议与房东确认并修改的条款（可直接发给房东）：\n" + "\n".join(lines)
