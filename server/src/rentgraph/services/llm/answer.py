"""上下文问答（P0-C）：合同/房源优先，引用必须存在，找不到依据就降级为通用建议。

两个安全底线（契约 §4.8 + PRD §3.1）：
- 引用存在性校验：citations 的 clause_no 必须在该合同条款集合里，否则剔除并降级措辞；
- html 白名单净化：模型/用户可控文本不得注入脚本、样式或事件属性。
"""

import asyncio
import html
import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

from .contracts import norm_text
from .mock import mock_answer
from .models import AnswerResult, ClauseData
from .prompts import ANSWER_PROMPT, ANSWER_STREAM_PROMPT
from .provider import LLMError, get_chat_model, provider_mode, structured_call

_TAG_RE = re.compile(r"<\s*(/?)\s*([a-zA-Z][a-zA-Z0-9]*)([^>]*)>")
_ALLOWED_TAGS = {"p", "br", "b", "strong", "i", "em", "span", "ul", "ol", "li", "code", "h3", "h4", "h5"}
# 只放行 class（图标/排版需要），且值必须落在安全字符集内；其余属性（on*、style、src）一律丢弃
_CLASS_RE = re.compile(r"""^\s*class\s*=\s*(?:"([A-Za-z0-9 _:./-]*)"|'([A-Za-z0-9 _:./-]*)')\s*$""")
_CLAUSE_REF_RE = re.compile(r"第\s*(\d+)\s*条")


def sanitize_html(raw: str) -> str:
    """白名单净化：保留结构标签与 class，标签外文本全部转义（XSS 与越权样式入口）"""
    out: list[str] = []
    pos = 0
    for m in _TAG_RE.finditer(raw):
        out.append(html.escape(raw[pos : m.start()]))
        pos = m.end()
        slash, name, attrs = m.group(1), m.group(2).lower(), m.group(3)
        if name not in _ALLOWED_TAGS:
            out.append(html.escape(m.group(0)))
            continue
        cls = _CLASS_RE.match(attrs)
        value = (cls.group(1) or cls.group(2)) if cls else ""
        out.append(f"<{slash}{name}" + (f' class="{value}"' if value else "") + ">")
    out.append(html.escape(raw[pos:]))
    return "".join(out)


def guard_citations(result: AnswerResult, clauses: Sequence[ClauseData]) -> AnswerResult:
    """引用存在性校验：不存在的条款引用剔除，并把语气降级为通用建议"""
    valid = {c.clause_no for c in clauses if c.clause_no is not None}
    kept = [c for c in result.citations if c.clause_no in valid]
    dropped = len(result.citations) - len(kept)
    result.citations = kept
    if result.mode == "context":
        # 正文里指向不存在条款的文字引用同样降级，避免「根据你的合同第 9 条」式幻觉
        result.html = _CLAUSE_REF_RE.sub(
            lambda m: m.group(0) if int(m.group(1)) in valid else "相关条款", result.html
        )
        if dropped:
            result.mode = "general"
            result.html += (
                '<p class="text-amber-600">合同中没有对应的具体条款，以上为通用建议，以合同原文为准。</p>'
            )
    return result


def _prompt(
    question: str,
    house: Mapping[str, Any] | None,
    clauses: Sequence[ClauseData],
    contract_id: str | None,
) -> str:
    context: dict[str, Any] = {
        "question": question,
        "contract_id": contract_id,
        "house": dict(house) if house else None,
        "clauses": [
            {"clause_no": c.clause_no, "title": c.title, "text": norm_text(c.text)[:300]}
            for c in clauses
            if c.clause_no is not None
        ],
    }
    return f"{ANSWER_PROMPT}\n\n上下文（JSON）：\n{json.dumps(context, ensure_ascii=False)}"


async def answer_question(
    question: str,
    house: Mapping[str, Any] | None,
    clauses: Sequence[ClauseData],
    contract_id: str | None,
) -> AnswerResult:
    question = question.strip()
    if not question:
        raise LLMError("EMPTY_QUESTION", "请输入要咨询的问题")
    if provider_mode() == "mock":
        result = mock_answer(question, house, clauses, contract_id)
    else:
        result = await structured_call(AnswerResult, _prompt(question, house, clauses, contract_id))
    result.html = sanitize_html(result.html)
    return guard_citations(result, clauses)


# ==================== 流式问答（真 token 流，边收边渲染） ====================

_OOS_RE = re.compile(r"买房|房价|走势|预测")
_LAW_RE = re.compile(r"法律|法规|民法典|政策|规定")
_LAW_SOURCES = ["flk.npc.gov.cn（国家法律法规数据库）"]
_FOLLOWUPS = ["刚毕业在上海租房要注意什么？", "房东不退押金怎么办？", "帮我看看这份租房合同有没有坑"]
_STREAM_STEP = 24  # mock 路径每片字符数（配合 30ms 间隔，肉眼可见的逐字输出）


def _stable_html(raw: str) -> str:
    """只对「标签已闭合到安全边界」的前缀做净化，避免把半个 `<b` 提前转义成 &lt;b。"""

    text = raw
    last_open = text.rfind("<")
    if last_open != -1 and ">" not in text[last_open:]:
        text = text[:last_open]  # 结尾是未闭合标签：先扣住，等下一片
    return sanitize_html(text)


def _followups_for(mode: str, house: Mapping[str, Any] | None, contract_id: str | None) -> list[str]:
    if mode in {"out_of_scope"}:
        return []
    if mode == "context":
        return ["物业费谁承担？", "提前退租要付什么？"]
    if house is not None and contract_id is None:
        return ["帮我核验这套房的承诺与合同", "这套房的真实成本是多少？"]
    return list(_FOLLOWUPS)


def _quoted_clauses(body: str, clauses: Sequence[ClauseData]) -> list[ClauseData]:
    """正文实际引用了哪些条款：显式「第 N 条」优先，其次用原文片段重合度兜底。

    真实模型有时会复述条款内容但不写条号；只要正文里出现了该条款的连续原文片段，
    就算引用成立（有据可查），避免把真实引用误判成「无依据」而降级。
    """

    compact = norm_text(body)
    valid = {c.clause_no: c for c in clauses if c.clause_no is not None}
    found: list[ClauseData] = []
    for number in dict.fromkeys(int(n) for n in _CLAUSE_REF_RE.findall(body)):
        clause = valid.get(number)
        if clause is not None and clause not in found:
            found.append(clause)
    if found:
        return found
    for clause in clauses:
        if clause.clause_no is None:
            continue
        text = norm_text(clause.text)
        window = 12
        for start in range(0, max(1, len(text) - window + 1), 6):
            if len(text) - start < window:
                break
            if text[start : start + window] in compact:
                found.append(clause)
                break
        if len(found) >= 3:
            break
    return found


def _stream_mode(question: str, body: str, clauses: Sequence[ClauseData], house: Mapping[str, Any] | None) -> str:
    """模式判定与引用一致：有真实条款且正文用到了它 → context；否则按上下文降级。"""

    if _OOS_RE.search(question):
        return "out_of_scope"
    if _quoted_clauses(body, clauses):
        return "context"
    if house is not None:
        return "house_only"
    return "general"


def _citations_from_body(body: str, clauses: Sequence[ClauseData], contract_id: str | None) -> list[Any]:
    """按正文真实用到的条款生成引用（只保留条款集合中存在的条款）。"""

    from .models import Citation

    return [
        Citation(
            clause_no=clause.clause_no,
            label=f"第 {clause.clause_no} 条",
            page=clause.page,
            char_start=clause.char_start,
            char_end=clause.char_end,
            contract_id=contract_id,
        )
        for clause in _quoted_clauses(body, clauses)[:3]
    ]


async def stream_answer(
    question: str,
    house: Mapping[str, Any] | None,
    clauses: Sequence[ClauseData],
    contract_id: str | None,
    sink: dict[str, Any],
) -> Any:
    """异步产出已净化的 HTML 片段；结束时把最终 AnswerResult 写进 `sink["result"]`。

    - openai：`ChatOpenAI.astream` 真流式，逐 delta 净化后产出（用户看到的是模型逐字输出）；
    - mock：整段答案分片产出（离线确定性，行为与真实模型一致：先流式、最后一并落库）。
    """

    question = question.strip()
    if not question:
        raise LLMError("EMPTY_QUESTION", "请输入要咨询的问题")

    raw = ""
    emitted = ""
    if provider_mode() == "mock":
        result = mock_answer(question, house, clauses, contract_id)
        body = sanitize_html(result.html)
        for index in range(0, len(body), _STREAM_STEP):
            chunk = body[index : index + _STREAM_STEP]
            emitted += chunk
            await asyncio.sleep(0.03)  # 让前端看得见逐字输出（mock 也保持同样的交互）
            yield chunk
        result.html = body
        sink["result"] = guard_citations(result, clauses)
        return

    model = get_chat_model()
    try:
        async for delta in model.astream(_stream_prompt(question, house, clauses, contract_id)):
            piece = delta.content
            if isinstance(piece, list):  # 多模态分片：只取文本
                piece = "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in piece)
            raw += str(piece or "")
            if not raw:
                continue
            safe = _stable_html(raw)
            if safe.startswith(emitted) and len(safe) > len(emitted):
                delta_text = safe[len(emitted) :]
                emitted = safe
                yield delta_text
    except LLMError:
        raise
    except Exception as exc:  # noqa: BLE001 - 网络/限流统一收敛，绝不回落 mock
        raise LLMError(
            "LLM_UNAVAILABLE",
            f"模型调用失败：{type(exc).__name__}: {str(exc)[:180]}",
            hint="检查 LLM_BASE_URL / LLM_API_KEY 与模型可用性后重试",
        ) from exc

    body = sanitize_html(raw)
    if not body.strip():
        raise LLMError("EMPTY_ANSWER", "模型没有返回内容", hint="请重试或换个问法")
    if body != emitted and body.startswith(emitted):
        yield body[len(emitted) :]
    result = AnswerResult(
        mode=_stream_mode(question, body, clauses, house),
        html=body,
        citations=_citations_from_body(body, clauses, contract_id),
        followups=_followups_for(_stream_mode(question, body, clauses, house), house, contract_id),
        sources=list(_LAW_SOURCES) if _LAW_RE.search(question) else [],
    )
    sink["result"] = guard_citations(result, clauses)


def _stream_prompt(
    question: str,
    house: Mapping[str, Any] | None,
    clauses: Sequence[ClauseData],
    contract_id: str | None,
) -> str:
    context: dict[str, Any] = {
        "question": question,
        "contract_id": contract_id,
        "house": dict(house) if house else None,
        "clauses": [
            {"clause_no": c.clause_no, "title": c.title, "text": norm_text(c.text)[:300]}
            for c in clauses
            if c.clause_no is not None
        ],
    }
    return f"{ANSWER_STREAM_PROMPT}\n\n上下文（JSON）：\n{json.dumps(context, ensure_ascii=False)}"


__all__ = ["answer_question", "guard_citations", "sanitize_html", "stream_answer"]
