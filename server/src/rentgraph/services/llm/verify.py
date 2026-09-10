"""房源承诺 × 合同条款的语义核验（P0-B 的 LLM 侧）。

只负责语义类问题（维修责任、口头承诺、模糊表述）：数值/日期/枚举类走确定性规则
（`services/verify_rules.py`），两条结果由上层合并。

铁律（PRD §3.3）：匹配不到条款必须是「未约定」，绝不允许推断成已承诺；
「一致」必须能指出唯一一个真实存在的条款号。
"""

from collections.abc import Sequence

from .contracts import norm_text
from .mock import mock_judge
from .models import ClauseData, PromiseItem, VerifyJudgement
from .prompts import VERIFY_PROMPT
from .provider import LLMError, provider_mode, structured_call


def guard_judgement(judgement: VerifyJudgement, clauses: Sequence[ClauseData]) -> VerifyJudgement:
    """后置校验：条款号必须存在；没有可依据的条款就不能给「一致」"""
    valid = {c.clause_no for c in clauses if c.clause_no is not None}
    if judgement.clause_no is not None and judgement.clause_no not in valid:
        judgement.clause_no = None
    if judgement.result == "一致" and judgement.clause_no is None:
        judgement.result = "未约定"
        judgement.severity = "high"
        judgement.advice = "合同中未找到对应条款，建议签约前把这条承诺写进合同或补充协议"
        judgement.reason = f"未在 {len(clauses)} 条条款中定位到可依据的约定，不得按已承诺处理"
    if judgement.result == "未约定":
        judgement.clause_no = None
    return judgement


def _prompt(claim: str, field: str, clauses: Sequence[ClauseData]) -> str:
    listing = "\n".join(
        f"[{c.clause_no}] {c.title}：{norm_text(c.text)[:300]}"
        for c in clauses
        if c.clause_no is not None
    )
    return (
        f"{VERIFY_PROMPT}\n\n房源承诺：{claim}\n对应字段：{field}\n"
        f"合同条款列表：\n{listing or '（无条款）'}\n"
    )


async def judge_promise(claim: str, field: str, clauses: Sequence[ClauseData]) -> VerifyJudgement:
    if not claim.strip():
        raise LLMError("EMPTY_CLAIM", "缺少待核验的承诺内容")
    promise = PromiseItem(claim=claim.strip(), field=field.strip())
    if provider_mode() == "mock":
        judgement = mock_judge(promise, clauses)
    elif not clauses:
        judgement = VerifyJudgement(
            result="未约定",
            severity="high",
            advice=f"合同没有可用条款，无法核验「{promise.field}」，建议先上传完整合同",
            reason="条款集合为空",
        )
    else:
        judgement = await structured_call(VerifyJudgement, _prompt(promise.claim, promise.field, clauses))
    return guard_judgement(judgement, clauses)


__all__ = ["guard_judgement", "judge_promise"]
