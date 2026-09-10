"""房源导入抽取（P0-A）：自由文本 / 批量文本 / 表格行 / docx 文本 → 候选房源草稿。

防幻觉是字段级的：每个提取到的字段都必须带一段能回到原文的 evidence 片段，
否则该字段作废（置 null 并计入 missing）。宁可让用户手工补一个字段，
也不能把一个编造的租金带进推荐（PRD §6.2：未确认字段不参与推荐）。
"""

import re

from .contracts import FIELD_LABELS, norm_text
from .mock import mock_extract_listings
from .models import ListingDraft, ListingExtraction
from .prompts import LISTING_PROMPT
from .provider import LLMError, provider_mode, structured_call

MAX_DRAFTS = 10  # 契约 §4.2：候选房源上限 10 套


# 合租/整租是硬约束的开关（PRD 场景 1：选择「允许合租」后合租房源才进入可推荐集合），
# 模型偶尔会把「合租次卧」判成整套出租，这里用确定性规则兜底（只认能回到原文的表述）。
_SHARED_RE = re.compile(r"合租|次卧|主卧|床位|单间|隔断")
_WHOLE_RE = re.compile(r"整租|开间|一居|两居|三居|四居|独立成套")


def apply_shared_rule(draft: ListingDraft, source_text: str) -> None:
    window = " ".join(draft.evidence.values()) or draft.name or ""
    if not window:
        window = source_text[:200]
    shared_hit = _SHARED_RE.search(window)
    if shared_hit:
        draft.shared = True
        draft.evidence.setdefault("shared", shared_hit.group(0))
    elif _WHOLE_RE.search(window):
        draft.shared = False
        draft.evidence.setdefault("shared", _WHOLE_RE.search(window).group(0))


def ground_draft(draft: ListingDraft, source_text: str) -> ListingDraft:
    """字段级 grounding + 缺失清单：evidence 无法在原文定位的字段一律作废"""
    compact = norm_text(source_text)
    kept: dict[str, str] = {}
    for field, snippet in draft.evidence.items():
        if field in FIELD_LABELS and snippet and norm_text(snippet) in compact:
            kept[field] = snippet
    for field in FIELD_LABELS:
        if field in kept:
            continue
        if getattr(draft, field) is not None:
            setattr(draft, field, None)  # 无证据支持的取值 → 丢弃，不许进确认面板
    draft.evidence = kept
    if not draft.name:
        head = norm_text(draft.raw or "")[:18]
        draft.name = head or norm_text(source_text)[:18] or "未命名房源"
    apply_shared_rule(draft, source_text)
    draft.missing = [label for field, label in FIELD_LABELS.items() if getattr(draft, field) is None]
    return draft


async def extract_listings(text: str, source: str) -> ListingExtraction:
    """统一入口：mock / openai 两条路径共用同一份 schema 与同一道 grounding 后置校验"""
    if not text.strip():
        raise LLMError("EMPTY_INPUT", "没有可解析的文本", hint="请粘贴房源信息或上传文件后重试")
    if provider_mode() == "mock":
        extraction = mock_extract_listings(text, source)
    else:
        extraction = await structured_call(ListingExtraction, LISTING_PROMPT + text[:12000])
    grounded = [ground_draft(d, text) for d in extraction.drafts]
    drafts = grounded[:MAX_DRAFTS]
    if not drafts or all(all(getattr(d, f) is None for f in FIELD_LABELS) for d in drafts):
        raise LLMError(
            "NO_LISTINGS",
            "未识别到房源信息",
            hint="请确保每套至少包含租金（如 5800/月）与户型或面积，一行一套",
        )
    return ListingExtraction(drafts=drafts, truncated=len(grounded) - len(drafts))


__all__ = ["MAX_DRAFTS", "extract_listings", "ground_draft"]
