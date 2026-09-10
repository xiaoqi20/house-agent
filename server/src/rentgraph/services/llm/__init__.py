"""LLM 契约层：结构化输出 + provider 选择 + 后置校验（grounding / 引用校验 / 数字校验）。

对外只暴露五个能力（契约 §3/§4）：
    extract_listings    房源字段抽取（P0-A 导入）
    extract_clauses     条款抽取 + 原文定位
    judge_promise       承诺 × 条款语义核验（P0-B）
    answer_question     上下文问答（P0-C）
    explain_recommendation  推荐解释（P0-A 三视图）

LLM_PROVIDER=mock 时全部走 `mock.py` 的确定性实现（离线测试与演示），
openai 时走真实模型；两条路径共用同一份 Pydantic schema 与同一道后置校验。
"""

from .answer import answer_question, guard_citations, sanitize_html
from .contracts import extract_clauses, grounding_ok, norm_text
from .explain import explain_recommendation, ground_numbers
from .listing import extract_listings
from .models import (
    AnswerResult,
    Citation,
    ClauseData,
    ClauseExtraction,
    ExplanationItem,
    ListingDraft,
    ListingExtraction,
    PromiseItem,
    RecommendationExplanation,
    VerifyJudgement,
)
from .provider import LLMError, get_chat_model, llm_available, provider_mode, with_schema
from .verify import judge_promise

__all__ = [
    "AnswerResult",
    "Citation",
    "ClauseData",
    "ClauseExtraction",
    "ExplanationItem",
    "LLMError",
    "ListingDraft",
    "ListingExtraction",
    "PromiseItem",
    "RecommendationExplanation",
    "VerifyJudgement",
    "answer_question",
    "explain_recommendation",
    "extract_clauses",
    "extract_listings",
    "get_chat_model",
    "ground_numbers",
    "grounding_ok",
    "guard_citations",
    "judge_promise",
    "llm_available",
    "norm_text",
    "provider_mode",
    "sanitize_html",
    "with_schema",
]
