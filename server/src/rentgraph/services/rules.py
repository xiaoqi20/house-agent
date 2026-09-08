import re
from collections.abc import Callable
from dataclasses import dataclass

from ..schemas.extraction import ClauseData


@dataclass
class RuleHit:
    rule_id: str
    level: str  # high | medium | low
    title: str
    reason: str
    suggestion: str
    ask: str = ""  # 发给房东的替换文本（谈判话术用），留空则由 suggestion 兜底


Rule = Callable[[ClauseData], "RuleHit | None"]

RULES: list[Rule] = []


def rule(fn: Rule) -> Rule:
    RULES.append(fn)
    return fn


@rule
def over_penalty(c: ClauseData) -> RuleHit | None:
    if c.clause_type == "违约金" and (c.months or 0) > 1:
        return RuleHit(
            "over-penalty", "high", "违约金过高",
            f"约定为 {c.months} 个月租金，显著高于行业惯例与司法实践支持的 1 个月上限",
            "将违约金修改为 1 个月租金",
            ask="违约金为一个月租金",
        )
    return None


@rule
def deposit_no_deadline(c: ClauseData) -> RuleHit | None:
    # 「15 日内 / 15 天内 / 3 个工作日内」都算约定了时限；只认“日”会误伤真实表述
    if c.clause_type == "押金" and "退还" in c.raw_text and not re.search(
        r"(\d+|[一二三四五六七八九十]+)\s*(?:个\s*工作日|工作日|日|天|个月)\s*内", c.raw_text
    ):
        return RuleHit(
            "deposit-no-deadline", "high", "押金退还条件模糊",
            "未约定退还时限，且“损坏”无扣款标准，退租时极易扯皮",
            "补充“租赁期满 15 日内退还押金”",
            ask="租赁期满或合同解除并结清费用后 15 日内，甲方一次性无息退还押金",
        )
    return None


@rule
def deposit_vague_damage(c: ClauseData) -> RuleHit | None:
    if c.clause_type == "押金" and "损" in c.raw_text and not re.search(r"折旧|凭证|市场价|清单", c.raw_text):
        return RuleHit(
            "deposit-vague-damage", "high", "押金扣款无标准",
            "以“损坏”作为扣押金依据，但无定价、折旧或凭证要求",
            "约定“损坏按市场价折旧扣款，需提供凭证”",
            ask="如有损坏，按市场价并考虑折旧后扣款，甲方需提供维修凭证或替换物品清单",
        )
    return None


@rule
def auto_renewal(c: ClauseData) -> RuleHit | None:
    if c.clause_type == "续租" and ("视为" in c.raw_text or "自动续" in c.raw_text) and "上浮" in c.raw_text:
        return RuleHit(
            "auto-renewal", "medium", "自动续约陷阱",
            "未提前书面通知即自动续租一年，且租金上浮",
            "删除自动续约，改为“续租需双方提前 30 日另行协商签约”",
            ask="续租需双方在期满前 30 日协商一致并重新签约，不约定自动续租与租金上浮",
        )
    return None


@rule
def repair_inverted(c: ClauseData) -> RuleHit | None:
    if c.clause_type == "维修" and "使用不当" in c.raw_text and "自然损耗" not in c.raw_text:
        return RuleHit(
            "repair-inverted", "medium", "维修责任全倒向租客",
            "只区分“使用不当”，未约定自然损耗由甲方维修",
            "补充“自然损耗及设施老化由甲方负责维修”",
            ask="自然损耗及设施老化由甲方负责维修并承担费用；因乙方使用不当造成的损坏由乙方承担",
        )
    return None


@rule
def unilateral_termination(c: ClauseData) -> RuleHit | None:
    if c.clause_type == "解约" and "甲方有权提前" in c.raw_text and "乙方有权提前" not in c.raw_text:
        return RuleHit(
            "unilateral-termination", "high", "提前解约单方特权",
            "仅约定甲方可提前解约，乙方无对等权利",
            "改为双方对等的提前解约条款",
            ask="甲乙双方均有权提前 30 日书面通知解约，并按相同标准承担违约责任",
        )
    return None


@rule
def sublease_ban(c: ClauseData) -> RuleHit | None:
    if c.clause_type == "转租" and re.search(r"不得转租|禁止转租", c.raw_text):
        return RuleHit(
            "sublease-ban", "low", "转租一刀切禁止",
            "任何转租均构成违约，换租/合租灵活性为零",
            "改为“经甲方书面同意可转租”",
            ask="经甲方书面同意，乙方可以全部或部分转租，甲方无正当理由不得拒绝",
        )
    return None


@rule
def long_prepay(c: ClauseData) -> RuleHit | None:
    if c.clause_type == "租金" and re.search(r"押[二三四五六]|[付预][四五六]|半年付|年付", c.raw_text):
        return RuleHit(
            "long-prepay", "medium", "支付周期过长",
            "预付周期超过 3 个月，资金占用与跑路风险高",
            "改为“押一付三”",
            ask="租金按“押一付三”支付，每期开始前 7 日支付下一期",
        )
    return None


@rule
def no_handover(c: ClauseData) -> RuleHit | None:
    if c.clause_type == "押金" and "交接" not in c.raw_text and "期满" in c.raw_text:
        return RuleHit(
            "no-handover", "medium", "缺退租交房流程",
            "押金退还是否挂钩交房验收，但合同未约定《房屋交接单》流程",
            "补充交房当天双方签署《房屋交接单》",
            ask="交房及退租当天双方共同验收并签署《房屋交接单》，写明水电气读数与物品清单",
        )
    return None


@rule
def unclear_fees(c: ClauseData) -> RuleHit | None:
    if c.clause_type == "租金" and not re.search(r"物业|水电|供暖|燃气|网络", c.raw_text):
        return RuleHit(
            "unclear-fees", "low", "隐性费用未列明",
            "未列明物业/水电/供暖/网络费用承担方",
            "在租金条款下列明各项费用归属",
            ask="在本条下增列：物业费由甲方承担，水电、燃气、供暖、网络费用由乙方按实际使用量承担",
        )
    return None


LEVEL_DEDUCTION = {"high": 12, "medium": 6, "low": 3}


def health_score(hits: list[RuleHit]) -> int:
    return max(0, 100 - sum(LEVEL_DEDUCTION[h.level] for h in hits))


def negotiation_script(hit: RuleHit, clause_no: int | None, clause_title: str | None = None) -> str:
    """谈判话术：条号 + 问题 + 建议替换文本。模板生成，不再调 LLM（一期够用，二期可换改写）"""
    ref = f"第 {clause_no} 条" if clause_no else "相关条款"
    subject = f"（{clause_title}）" if clause_title else ""
    ask = hit.ask or hit.suggestion
    return (
        f"房东您好，{ref}{subject}想跟您商量一下：{hit.reason}。"
        f"我的想法是把这条改成“{ask}”。其余条款我都没意见，您看这样调整可以吗？"
    )
