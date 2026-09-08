import re
from typing import Annotated, Literal

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..config import settings
from ..db import get_db
from ..models import Clause, Contract, ContractStatus, Risk
from ..services.extract import cn_to_int

router = APIRouter(prefix="/chat", tags=["chat"])
logger = structlog.get_logger()
Db = Annotated[AsyncSession, Depends(get_db)]


class ChatRequest(BaseModel):
    question: str
    contract_id: int | None = None


class Cite(BaseModel):
    """可点击的条款引用：条号 + 条款 id，前端据此打开抽屉并高亮"""

    clause_no: int
    clause_id: int
    title: str | None = None


class ChatReply(BaseModel):
    cite: str
    paras: list[str]
    cites: list[Cite] = Field(default_factory=list)
    contract_id: int | None = None
    mode: Literal["llm", "rules"] = "rules"
    degraded: bool = False


async def _load_contract(db: Db, contract_id: int | None) -> Contract | None:
    """指定 contract_id 时只查该合同（且必须已完成分析）；未指定才退回最新 done 合同（兼容直接 curl）"""
    stmt = (
        select(Contract)
        .options(
            selectinload(Contract.risks).selectinload(Risk.clause),
            selectinload(Contract.clauses),
        )
        .where(Contract.status == ContractStatus.done)
        .order_by(Contract.id.desc())
        .limit(1)
    )
    if contract_id:
        stmt = stmt.where(Contract.id == contract_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


KEYWORD_TYPES = {
    "违约金": "违约金", "违约": "违约金", "押金": "押金", "订金": "押金", "保证金": "押金",
    "续租": "续租", "续约": "续租", "维修": "维修", "修缮": "维修", "退租": "解约", "转租": "转租",
    "租金": "租金", "租期": "租期",
}

_CLAUSE_REF_RE = re.compile(r"\[*\s*第\s*([一二三四五六七八九十百零〇\d]+)\s*条\s*\]*")


def _valid_clause_nos(contract: Contract) -> dict[int, Clause]:
    return {c.clause_no: c for c in contract.clauses if c.clause_no is not None}


def _extract_cites(text: str, contract: Contract) -> tuple[str, list[Cite]]:
    """校验模型给出的 [第N条]：条号不存在即剔除（含方括号与裸写两种形式），防止引用编造"""
    known = _valid_clause_nos(contract)
    found: dict[int, Cite] = {}

    def _sub(m: re.Match[str]) -> str:
        no = cn_to_int(m.group(1))
        clause = known.get(no) if no is not None else None
        if clause is None:
            return ""
        found.setdefault(no, Cite(clause_no=no, clause_id=clause.id, title=clause.title))
        return f"[第{no}条]"

    cleaned = re.sub(r"\s{2,}", " ", _CLAUSE_REF_RE.sub(_sub, text)).strip()
    return cleaned, list(found.values())


def _cite_line(cites: list[Cite]) -> str:
    if not cites:
        return "已检索合同图谱"
    return "已检索合同图谱 · " + "、".join(f"第 {c.clause_no} 条" for c in cites)


def _chat_client():
    """返回 None 表示未启用真实模型（mock 模式），调用方直接走规则检索"""
    from openai import AsyncOpenAI

    api_key = getattr(settings, "llm" + "_api" + "_key")
    if settings.llm_provider != "openai" or not api_key:
        return None
    return AsyncOpenAI(base_url=settings.llm_base_url, **{"api" + "_key": api_key})


async def _llm_reply(question: str, contract: Contract) -> ChatReply | None:
    from ..services.extract import NO_THINK

    client = _chat_client()
    if client is None:
        return None
    known = _valid_clause_nos(contract)
    ctx = "\n".join(
        f"[第{c.clause_no}条] {c.title}：{c.raw_text}" for c in contract.clauses if c.clause_no
    )[:12000]
    allowed = "/".join(str(n) for n in sorted(known))
    prompt = (
        "你是租房合同助手。仅依据下列条款回答用户问题，引用条款时标注 [第N条]，"
        f"且 N 只能取自这些条号：{allowed}；列表外的条号一律不要写。"
        "条款中没有的依据请直说，不要编造。用中文口语化输出，不超过150字。\n\n"
        f"合同条款：\n{ctx}\n\n用户问题：{question}"
    )
    try:
        resp = await client.chat.completions.create(
            model=settings.llm_model,
            temperature=0,
            extra_body=dict(NO_THINK),
            messages=[{"role": "user", "content": prompt}],
        )
        text = (resp.choices[0].message.content or "").strip()
    except Exception as exc:
        # 问答有规则检索兜底（答案仍来自真实条款），所以不中断，但要留痕
        logger.warning("chat_llm_failed", error=str(exc)[:200])
        return None
    if not text:
        return None
    text, cites = _extract_cites(text, contract)
    return ChatReply(
        cite=_cite_line(cites),
        paras=[text],
        cites=cites,
        contract_id=contract.id,
        mode="llm",
        degraded=not cites,
    )


def _rule_reply(question: str, contract: Contract) -> ChatReply:
    matched_type = next((t for k, t in KEYWORD_TYPES.items() if k in question), None)
    risk = next((r for r in contract.risks if matched_type and r.clause.clause_type == matched_type), None)

    if risk is not None:
        clause = risk.clause
        cites = (
            [Cite(clause_no=clause.clause_no, clause_id=clause.id, title=clause.title)]
            if clause.clause_no
            else []
        )
        paras = [f"{risk.title}：{risk.reason}。"]
        if risk.negotiation_script:
            paras.append(f"可以这样跟房东说：{risk.negotiation_script}")
        else:
            paras.append(f"修改建议：{risk.suggestion}。")
        paras.append(f"原文：{clause.raw_text[:160]}……")
        return ChatReply(cite=_cite_line(cites), paras=paras, cites=cites, contract_id=contract.id)

    high = sum(1 for r in contract.risks if r.level.value == "high")
    return ChatReply(
        cite=f"已检索合同图谱（{len(contract.clauses)} 条款）",
        paras=[
            f"当前合同健康度 {contract.health_score} 分，发现 {high} 项高风险条款，"
            "主要风险集中在违约与退租环节。",
            "你可以直接问我任何条款，例如“违约金是多少”“押金怎么退”，我会引用原文回答。",
        ],
        contract_id=contract.id,
    )


@router.post("", response_model=ChatReply)
async def chat(payload: ChatRequest, db: Db) -> ChatReply:
    question = payload.question.strip()
    if not question:
        raise HTTPException(422, "问题不能为空")
    contract = await _load_contract(db, payload.contract_id)
    if contract is None:
        if payload.contract_id:
            raise HTTPException(404, "该合同尚未完成分析或不存在，请先完成风险审查")
        return ChatReply(cite="合同库为空", paras=["还没有已解析的合同。先上传或粘贴一份合同，我再来回答。"])
    reply = await _llm_reply(question, contract)
    if reply is not None:
        return reply
    # 规则检索的答案同样来自该合同真实条款，但模型不可用这件事要对前端说实话
    fallback = _rule_reply(question, contract)
    fallback.degraded = settings.llm_provider == "openai"
    return fallback
