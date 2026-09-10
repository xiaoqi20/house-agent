"""mock 路径的确定性实现（LLM_PROVIDER=mock 或单元测试）。

- 房源解析：逐字搬运前端 `web/src/data/demo.ts` parseHousesInput 的正则语义，
  保证「粘贴 5 条演示房源」得到与原型完全一致的字段值（同一套文案口径）。
- 条款切分：contracts.mock_extract（一期正则原样搬运）。
- 核验 / 问答 / 解释：键值比较与确定性模板，离线可复现；数字只来自确定性计算结果。

注意：本模块 html 里的用户可控文本不做手工转义，统一由 answer.sanitize_html 在出口白名单净化，
避免二次转义（`&amp;` 再转义成 `&amp;amp;`）。
"""

import re
from collections.abc import Mapping, Sequence
from typing import Any

from .contracts import AMOUNT_RE, CLAUSE_HEAD_RE, cn_to_int, norm_text
from .models import (
    AnswerResult,
    Citation,
    ClauseData,
    ExplanationItem,
    ListingDraft,
    ListingExtraction,
    PromiseItem,
    RecommendationExplanation,
    VerifyJudgement,
)
from .table import table_rows_to_drafts

# ============================ 房源解析（前端正则语义搬运） ============================

_LINE_SPLIT_RE = re.compile(r"[\n;；]+")
_MARKER_RE = re.compile(r"[①②③④⑤⑥⑦⑧⑨⑩]|(?<!\d)\d+[.、](?!\d)")
_MARKER_SPLIT_RE = re.compile(
    r"(?=[①②③④⑤⑥⑦⑧⑨⑩]|(?<!\d)\d+[.、](?!\d)|(?<!\d)[(（\[【]\d+[)）\]】]"
    r"|(?:^|\s)房源[A-Za-z0-9一二三四五六]?[：:])"
)
_PREFIX_RE = re.compile(
    r"^(?:[①②③④⑤⑥⑦⑧⑨⑩]|(?:\d+|[一二三四五六七八九十])[.、\s]+"
    r"|[(（\[【]?\d+[)）\]】]|房源[A-Za-z0-9一二三四五六]?[：:]\s*)+"
)
_NON_HOUSE_HEAD_RE = re.compile(r"^(?:我输入|帮我|请帮|房源对比|有三套|这几套|三套房源|房源如下|对比)")
_HOUSE_SIGNAL_RE = re.compile(r"(?:平|㎡|开间|次卧|主卧|一居|两居|/月)")
_PRICE_HINT_RE = re.compile(r"(?:\d{3,5}\s*(?:/月|元/月|元)|押[一二三两]付)", re.I)
_TYPE_AREA_RE = re.compile(r"(?:\d+(?:\.\d+)?\s*(?:平|㎡|平米)|一居|两居|三居|四居|开间|次卧|主卧|合租|整租)")
_COMMUTE_FLOOR_RE = re.compile(r"(?:地铁|\d+\s*分钟|\d+楼|\d+层|[东西南北]向)")

_RENT_RE = re.compile(r"(\d{3,5})\s*(?:/月|元/月|元)")
_DEPOSIT_RE = re.compile(r"(押[一二三两]付[一二三两月六]+|无押金)")
_AREA_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:平米|平|㎡)")
_COMMUTE_RE = re.compile(r"(?:地铁\s*|通勤\s*约?)?(\d{1,3})\s*分钟")
_FLOOR_RE = re.compile(r"(\d+(?:/\d+)?(?:楼|层))")
_ORIENT_RE = re.compile(r"([东西南北]+向)")
_LAYOUT_RE = re.compile(
    r"((?:一|两|三|四)居(?:合租|整租)?(?:次卧|主卧)?|开间|(?:合租|整租)(?:次卧|主卧)|(?:次卧|主卧))"
)
_PROPERTY_FEE_RE = re.compile(r"物业费\s*(\d{2,4})")
_PROPERTY_BEAR_RE = re.compile(r"物业费.{0,6}(房东|甲方)承担|房东承担物业")
_PROPERTY_TENANT_RE = re.compile(r"物业费.{0,6}(租客|乙方|自己)承担|自付物业")
_AVAILABLE_RE = re.compile(r"(\d{1,2}月\d{1,2}日|随时|尽快)(?:可)?入住")
_METRO_RE = re.compile(r"(\d+号线\S{0,10}站)")
_NAME_TAIL_RE = re.compile(r"(\d{3,5}\s*(?:/月|元).*$)")
_NAME_DEPOSIT_RE = re.compile(r"(?:押[一二三两]付.*$)")
_NAME_HEAD_RE = re.compile(r"^([^\d,，\s/]+)")


def _is_house_line(part: str) -> bool:
    if _NON_HOUSE_HEAD_RE.match(part) and not _HOUSE_SIGNAL_RE.search(part):
        return False
    has_price = bool(_PRICE_HINT_RE.search(part))
    has_type_or_area = bool(_TYPE_AREA_RE.search(part))
    has_commute_or_floor = bool(_COMMUTE_FLOOR_RE.search(part))
    return (
        (has_price and has_type_or_area)
        or (has_price and has_commute_or_floor)
        or (has_type_or_area and has_commute_or_floor)
    )


def _split_lines(text: str) -> list[str]:
    parts = [s.strip() for s in _LINE_SPLIT_RE.split(text)]
    parts = [p for p in parts if p]
    if len(parts) <= 2 and _MARKER_RE.search(text):
        parts = [s.strip() for s in _MARKER_SPLIT_RE.split(text)]
        parts = [p for p in parts if p]
    return [p for p in parts if _is_house_line(p)]


def _name_of(clean: str, idx: int) -> str:
    name = _NAME_TAIL_RE.sub("", clean)
    name = _NAME_DEPOSIT_RE.sub("", name)
    name = re.sub(r"[，,;；]", " ", name).strip()
    if len(name) < 2:
        m = _NAME_HEAD_RE.match(clean)
        name = m.group(1) if m else f"房源 {idx + 1}"
    return name[:18]


def _parse_one(part: str, idx: int) -> ListingDraft:
    clean = _PREFIX_RE.sub("", part).strip()
    values: dict[str, Any] = {"raw": clean}
    evidence: dict[str, str] = {}

    def put(field: str, value: Any, snippet: str) -> None:
        if value is None:
            return
        values[field] = value
        evidence[field] = snippet

    m = _RENT_RE.search(clean)
    if m:
        put("rent", int(m.group(1)), m.group(0))
    m = _DEPOSIT_RE.search(clean)
    if m:
        put("deposit", m.group(1), m.group(0))
    m = _AREA_RE.search(clean)
    if m:
        put("area", float(m.group(1)), m.group(0))
    m = _COMMUTE_RE.search(clean)
    if m:
        put("commute_min", int(m.group(1)), m.group(0))
    m = _FLOOR_RE.search(clean)
    if m:
        put("floor", m.group(1), m.group(0))
    m = _ORIENT_RE.search(clean)
    if m:
        put("orientation", m.group(1), m.group(0))
    m = _LAYOUT_RE.search(clean)
    if m:
        put("layout", m.group(1), m.group(0))
    m = re.search(r"独立卫浴|独卫", clean)
    if m:
        put("bathroom", True, m.group(0))
    m = re.search(r"无独卫|公用卫浴|共用卫浴", clean)
    if m:
        put("bathroom", False, m.group(0))
    m = re.search(r"合租|次卧|主卧", clean)
    if m:
        put("shared", True, m.group(0))
    if "整租" in clean:
        put("shared", False, "整租")
    m = re.search(r"允许养|可养|宠物友好", clean)
    if m:
        put("pet", "允许宠物", m.group(0))
    else:
        m = re.search(r"禁止养|不可养|不许养", clean)
        if m:
            put("pet", "禁止宠物", m.group(0))
    m = re.search(r"(?:网费|网络费|宽带费)\s*([\d]{2,5})", clean)
    if m:
        put("net_fee", int(m.group(1)), m.group(0))
    m = _PROPERTY_FEE_RE.search(clean)
    if m:
        put("property_fee", int(m.group(1)), m.group(0))
    m = _PROPERTY_BEAR_RE.search(clean)
    if m:
        put("property_bear", "房东承担", m.group(0))
    else:
        m = _PROPERTY_TENANT_RE.search(clean)
        if m:
            put("property_bear", "租客承担", m.group(0))
    m = _AVAILABLE_RE.search(clean)
    if m:
        # 原型此处拼接出「随时可可入住」的重复字，后端按同样口径去掉重复：group(1) + 可入住
        put("available", f"{m.group(1)}可入住", m.group(0))
    m = _METRO_RE.search(clean)
    if m:
        put("metro", m.group(1), m.group(0))
    m = re.search(r"采光好|采光佳", clean)
    if m:
        put("lighting", "采光好", m.group(0))
    name = _name_of(clean, idx)
    if name:
        put("name", name, name)
    # 置信度 = 有原文证据的字段占比（确定性口径，不伪造高置信）
    values["confidence"] = round(len(evidence) / 28, 2)
    return ListingDraft(**values, evidence=evidence)


def mock_extract_listings(text: str, source: str) -> ListingExtraction:
    """source 只为与 extract_listings 口径一致；来源归因由上层写入 House.source（W2 落库）

    条款切分的 mock 实现是 contracts.mock_extract（两条路径共用同一份正则与 grounding）。
    """
    # 表格型输入（Excel/CSV → rows_to_text）优先走确定性列名映射：
    # 否则「小区: 望京花园 | 租金: 5800」这类行会被自由文本正则整行丢弃（PRD §3.1 要求支持 xlsx/csv）
    tabular = table_rows_to_drafts(text, source)
    if tabular:
        return ListingExtraction(drafts=tabular)
    drafts = [_parse_one(part, i) for i, part in enumerate(_split_lines(text))]
    return ListingExtraction(drafts=drafts)


# ============================ 承诺 × 条款核验（键值比较） ============================

FIELD_KEYWORDS: dict[str, tuple[str, ...]] = {
    "租金": ("租金", "月租"),
    "押金/付款方式": ("押金", "保证金", "支付"),
    "物业费": ("物业",),
    "物业费承担方": ("物业",),
    "维修": ("维修", "修缮"),
    "违约金": ("违约金",),
    "租期": ("租期", "租赁期"),
    "租期要求": ("租期", "租赁期"),
    "宠物": ("宠物", "饲养"),
    "转租": ("转租",),
    "整租/合租": ("合租", "整租"),
    "中介费": ("中介费", "居间"),
    "可入住时间": ("入住", "交付"),
    "独立卫浴": ("卫生间", "卫浴", "浴室"),
}

_PAY_RE = re.compile(r"押\s*([一二两三])\s*付\s*([一二两三])")
_PENALTY_RE = re.compile(r"违约金[^。；]{0,20}?([一二两三四五六七八九十\d]+)\s*(?:个)?月")
_VAGUE_RE = re.compile(r"口头|大概|大约|应该|可能|尽量|待|据说|说好")


# 字段 → 期望的条款类型：命中的条款里有同类型条款时优先（避免「押金」被含「支付」的租金条款劫持）
FIELD_TYPES: dict[str, str] = {
    "租金": "租金",
    "押金/付款方式": "押金",
    "违约金": "违约金",
    "租期": "租期",
    "租期要求": "租期",
    "维修": "维修",
    "转租": "转租",
}


def match_clauses(field: str, clauses: Sequence[ClauseData]) -> list[ClauseData]:
    """按字段关键词找候选条款：命中即「合同里提过这件事」，同类型条款优先"""
    keywords = FIELD_KEYWORDS.get(field) or tuple(k for k in (field,) if k)
    hits = [c for c in clauses if any(k in c.text or k in c.title for k in keywords)]
    want = FIELD_TYPES.get(field)
    return sorted(
        hits,
        key=lambda c: (
            0 if want and c.clause_type == want else 1,
            c.clause_no is None,
            c.clause_no or 0,
        ),
    )


def _keys(text: str) -> dict[str, float]:
    """可比较键值：金额（元）、押/付月数、违约金月数。条号先剥掉，避免把「第五条」当成金额"""
    t = CLAUSE_HEAD_RE.sub("", text)
    out: dict[str, float] = {}
    m = AMOUNT_RE.search(t)
    if m:
        out["金额"] = float(m.group(1).replace(",", "").replace("，", ""))
    m = _PAY_RE.search(t)
    if m:
        out["押金月数"] = float(cn_to_int(m.group(1)) or 0)
        out["付款月数"] = float(cn_to_int(m.group(2)) or 0)
    m = _PENALTY_RE.search(t)
    if m:
        months = cn_to_int(m.group(1))
        if months:
            out["违约金月数"] = float(months)
    return out


def mock_judge(promise: PromiseItem, clauses: Sequence[ClauseData]) -> VerifyJudgement:
    hits = match_clauses(promise.field, clauses)
    if not hits:
        return VerifyJudgement(
            result="未约定",
            severity="high",
            clause_no=None,
            advice=f"合同里没有关于「{promise.field}」的约定，建议签约前写进合同或补充协议",
            reason=f"在 {len(clauses)} 条条款中未找到与「{promise.field}」相关的约定，不得按已承诺处理",
        )
    clause = hits[0]
    ref = f"第 {clause.clause_no} 条" if clause.clause_no else "相关条款"
    claim_keys, clause_keys = _keys(promise.claim), _keys(clause.text)
    shared = [k for k in claim_keys if k in clause_keys]
    if shared:
        diff = [k for k in shared if claim_keys[k] != clause_keys[k]]
        if diff:
            return VerifyJudgement(
                result="冲突",
                severity="high",
                clause_no=clause.clause_no,
                advice=f"{ref}约定与「{promise.claim}」不一致，签约前建议改回与沟通一致的版本",
                reason="；".join(
                    f"{k}：房源 {claim_keys[k]:g} vs 合同 {clause_keys[k]:g}" for k in diff
                ),
            )
        return VerifyJudgement(
            result="一致",
            severity="low",
            clause_no=clause.clause_no,
            advice=f"「{promise.claim}」与{ref}一致，保留该表述即可",
            reason=f"{ref}约定：" + "；".join(f"{k} {clause_keys[k]:g}" for k in shared),
        )
    if norm_text(promise.claim) in norm_text(clause.text):
        return VerifyJudgement(
            result="一致",
            severity="low",
            clause_no=clause.clause_no,
            advice=f"「{promise.claim}」已写入{ref}，保留原文即可",
            reason=f"{ref}原文包含该表述",
        )
    vague = "（含模糊/口头表述）" if _VAGUE_RE.search(promise.claim) else ""
    return VerifyJudgement(
        result="无法判断",
        severity="medium",
        clause_no=clause.clause_no,
        advice=f"{ref}未明确「{promise.field}」的责任划分，建议让房东写进补充条款再签约",
        reason=f"{ref}提到相关事项但无可对齐的数值/责任约定{vague}，需书面确认",
    )


# ============================ 上下文问答（前端 answers.ts 文案口径） ============================


def _t(title: str, icon: str, cls: str, body: str) -> str:
    head = (
        '<p class="font-medium text-gray-900 mb-1.5 flex items-center gap-1.5">'
        f'<i class="fas {icon} {cls}"></i> {title}</p>'
    )
    return head + body


def _money(v: Any) -> str:
    try:
        return f"{int(v):,}"
    except (TypeError, ValueError):
        return str(v)


def _bear_text(bear: Any, fee: Any) -> str:
    """物业费承担方展示口径：有承担方写承担方，否则退到金额，再退到待确认"""
    if bear:
        return str(bear)
    return f"物业费 {_money(fee)} 元/月" if fee is not None else "待确认"


def _minute_text(minutes: Any) -> str:
    return f"{minutes} 分钟" if minutes is not None else "待确认"


def _field(obj: Mapping[str, Any] | None, *names: str) -> Any:
    """读取房源/偏好字段：兼容后端 HouseOut(snake_case) 与前端 House(camelCase)"""
    if not obj:
        return None
    for n in names:
        if obj.get(n) is not None:
            return obj[n]
    return None


def _brief(text: str, limit: int = 90) -> str:
    t = " ".join(text.split())
    return t if len(t) <= limit else t[:limit] + "…"


def _find_clause(clauses: Sequence[ClauseData], keywords: Sequence[str]) -> ClauseData | None:
    for c in sorted(clauses, key=lambda c: (c.clause_no is None, c.clause_no or 0)):
        if any(k in c.text or k in c.title for k in keywords):
            return c
    return None


def _citation(clause: ClauseData | None, contract_id: str | None) -> Citation | None:
    if clause is None or clause.clause_no is None:
        return None
    return Citation(
        clause_no=clause.clause_no,
        label=f"第 {clause.clause_no} 条",
        page=clause.page,
        char_start=clause.char_start,
        char_end=clause.char_end,
        contract_id=contract_id,
    )


OOS_HTML = _t(
    "超出当前能力范围",
    "fa-circle-minus",
    "text-gray-400",
    "我专注于<b>租房决策</b>（候选房源比较、合同核验、租房常识），不做房价走势预测——"
    "这类问题缺乏可核实的依据，我不想给你看似确定的误导性结论。",
)

LAW_HTML = _t(
    "法规政策 · 请注意适用范围",
    "fa-scale-balanced",
    "text-brand-600",
    "与租房最相关的是《中华人民共和国民法典》合同编租赁合同章节（第 703—734 条），"
    "例如第 710 条：承租人按约定方法使用租赁物致损耗的，不承担赔偿责任。<br><br>"
    "<b>来源：</b>国家法律法规数据库（flk.npc.gov.cn） · "
    "<b>适用范围：</b>全国，地方性租赁条例可能另有规定。<br>"
    '<span class="text-amber-600"><i class="fas fa-triangle-exclamation mr-1"></i>'
    "涉及具体纠纷时，请以官方文本为准或咨询专业人士；以上为一般性科普，不构成法律结论。</span>",
)

LAW_SOURCES = ["flk.npc.gov.cn（国家法律法规数据库）"]

KNOWLEDGE_HTML = _t(
    "租房知识 · 通用建议（当前无房源 / 合同上下文）",
    "fa-book-open",
    "text-brand-600",
    "这个问题我可以帮你拆解。为了给出更贴合的建议，可以补充一下：你所在的<b>城市</b>、"
    "目前处于<b>看房 / 已签约 / 租住中 / 退租</b>哪个阶段？<br><br>"
    "如果手里有候选房源或合同，也可以先导入 / 绑定，我会结合具体内容回答。",
)

_FOLLOWUP = ["我所在的城市是？（用于地区差异）", "我现在的阶段：看房 / 已签约 / 租住中 / 退租"]


def _bear_of_clause(text: str) -> str | None:
    if re.search(r"(甲方|房东|出租方)[^。；]{0,8}承担", text):
        return "房东承担"
    if re.search(r"(乙方|租客|承租方)[^。；]{0,8}承担", text):
        return "租客承担"
    return None


def mock_answer(
    question: str,
    house: Mapping[str, Any] | None,
    clauses: Sequence[ClauseData],
    contract_id: str | None,
) -> AnswerResult:
    if re.search(r"买房|房价|走势|预测", question):
        return AnswerResult(mode="out_of_scope", html=OOS_HTML)
    if re.search(r"法律|法规|民法典|政策|规定", question):
        return AnswerResult(
            mode="general", html=LAW_HTML, sources=list(LAW_SOURCES), followups=list(_FOLLOWUP)
        )

    if "物业费" in question:
        clause = _find_clause(clauses, ("物业",))
        citation = _citation(clause, contract_id)
        if citation is not None and clause is not None and house is not None:
            bear_in_clause = _bear_of_clause(clause.text)
            house_bear = _field(house, "property_bear", "propertyBear")
            house_fee = _field(house, "property_fee", "propertyFee")
            conflict = bool(bear_in_clause and house_bear and bear_in_clause != house_bear)
            body = (
                f"{citation.label} 约定：{_brief(clause.text)}。<br>"
                f"你的房源 {_field(house, 'no') or ''} 记录的是「"
                f"{_bear_text(house_bear, house_fee)}」"
            )
            if conflict:
                body += '，两者<b class="text-red-600">冲突</b>。'
            else:
                body += "。<br>"
            body += (
                "<br><b>建议：</b>签约前把物业费承担方写回与沟通一致的版本；如果房东不愿修改，"
                f"至少把金额 {_money(house_fee) + ' 元/月' if house_fee is not None else '（待确认）'} "
                "写进合同，避免后期加价。"
            )
            return AnswerResult(
                mode="context",
                html=_t(
                    f"结合你的合同与房源 · 引用 {citation.label}",
                    "fa-check-circle",
                    "text-green-500",
                    body,
                ),
                citations=[citation],
            )
        if house is not None:
            house_bear = _field(house, "property_bear", "propertyBear")
            house_fee = _field(house, "property_fee", "propertyFee")
            fee_text = (
                f"{_money(house_fee)} 元/月"
                if house_fee is not None
                else '<span class="text-amber-600">待确认</span>'
            )
            body = (
                f"房源记录：物业费 {fee_text}{('，' + str(house_bear)) if house_bear else ''}。<br><br>"
                "注意：这只是房源侧信息，<b>最终要以合同条款为准</b>。绑定合同后我可以逐项核验是否一致。"
            )
            return AnswerResult(
                mode="house_only",
                html=_t(
                    f"基于当前房源 {_field(house, 'no') or ''}（尚未绑定合同）",
                    "fa-building",
                    "text-emerald-500",
                    body,
                ),
            )
        body = (
            "物业费承担没有统一规定，常见三种：房东全包、租客全付、按约定分摊。"
            "<b>关键是在合同里写清楚金额与承担方</b>，口头承诺退租时很难举证。<br><br>"
            "你目前在哪个城市、处于看房还是已签约阶段？有合同的话可以直接绑定，我帮你看具体条款。"
        )
        return AnswerResult(
            mode="general",
            html=_t("租房知识 · 通用建议", "fa-book-open", "text-brand-600", body),
            followups=list(_FOLLOWUP),
        )

    if re.search(r"退租|解约|提前退", question):
        clause = _find_clause(clauses, ("违约金", "解除", "退租", "解约"))
        citation = _citation(clause, contract_id)
        if citation is not None and clause is not None:
            body = (
                f"你的合同没有单独的「提前退租」条款，但 {citation.label} 约定：{_brief(clause.text)}。<br>"
                "提前退租在合同法理上常被认定为违约并适用该条。<br><br>"
                "<b>法律依据与酌减参考：</b>根据《中华人民共和国民法典》第五百八十五条第二款及相关司法解释，"
                "约定的违约金过分高于造成的损失的，当事人可以请求人民法院或者仲裁机构予以适当减少。"
                "实践中通常以房东因提前解约产生的实际直接损失（如房屋重新出租合理空置期，通常在 1 个月左右）"
                "为衡量基础，具体视个案证据综合认定，不宜直接推定为某一固定减免标准。<br><br>"
                "<b>签约协商建议（非确定性裁判结论）：</b>建议签约前协商将违约金修改为 1 个月租金，"
                "并补充「提前 30 日书面通知且协助转租可免责退押金」。"
            )
            return AnswerResult(
                mode="context",
                html=_t(f"优先引用你的合同 · {citation.label}", "fa-check-circle", "text-green-500", body),
                citations=[citation],
            )
        if house is not None:
            body = (
                "提前退租的成本主要看合同里的<b>违约金条款</b>和<b>押金退还条件</b>，这些房源信息里没有。"
                "建议先绑定合同，我可以帮你定位对应条款。<br><br>"
                "<b>通用经验：</b>提前 30 日书面通知、配合找到下家、保留沟通记录，能显著降低纠纷风险。"
                "具体权利义务以最终签订的合同为准。"
            )
            return AnswerResult(
                mode="house_only",
                html=_t(
                    f"当前只有房源 {_field(house, 'no') or ''}，未绑定合同",
                    "fa-building",
                    "text-emerald-500",
                    body,
                ),
            )
        body = (
            "提前退租一般涉及：① 违约金约定；② 押金结算退还；③ 转租免责约定。<br><br>"
            "你所在的城市和租住阶段是？有合同可以绑定后我给你逐条分析。"
        )
        return AnswerResult(
            mode="general",
            html=_t("租房知识 · 通用建议", "fa-book-open", "text-brand-600", body),
            followups=list(_FOLLOWUP),
        )

    if "违约金" in question:
        clause = _find_clause(clauses, ("违约金",))
        citation = _citation(clause, contract_id)
        if citation is not None and clause is not None:
            body = (
                f"{citation.label} 约定：{_brief(clause.text)}。<br><br>"
                "<b>法律依据与考量依据：</b>根据《民法典》第五百八十五条及《最高人民法院关于适用〈民法典〉"
                "合同编通则若干问题的解释》第六十五条，约定的违约金超过造成损失的百分之三十的，"
                "一般可以认定为“过分高于造成的损失”。裁判中通常以房东实际空置期损失为基础进行综合裁量，"
                "具体视实际损失、合同履行情况等认定，不构成确定性胜诉或调减结论。<br><br>"
                "<b>协商话术参考（仅供沟通建议）：</b>“三个月租金作为违约金相对偏高，签约前建议参考行业通常做法"
                "调整为一个月的违约金标准，双方履行都更安心。”"
            )
            return AnswerResult(
                mode="context",
                html=_t(f"已检索你的合同 · 引用 {citation.label}", "fa-check-circle", "text-green-500", body),
                citations=[citation],
            )
        return AnswerResult(mode="general", html=KNOWLEDGE_HTML, followups=list(_FOLLOWUP))

    if "押金" in question:
        clause = _find_clause(clauses, ("押金", "保证金"))
        citation = _citation(clause, contract_id)
        if citation is not None and clause is not None:
            body = (
                f"{citation.label} 约定：{_brief(clause.text)}。<br><br>"
                "<b>证据链建议：</b>① 入住拍全屋视频并让房东确认；② 退租前 7 日书面通知；"
                "③ 交房当天双方签《房屋交接单》。"
            )
            return AnswerResult(
                mode="context",
                html=_t(f"结合你的合同 · 引用 {citation.label}", "fa-check-circle", "text-green-500", body),
                citations=[citation],
            )
        body = (
            "退押金关键在<b>证据链</b>：① 入住时拍全屋视频并让房东确认；② 退租前 7 日发书面《退租通知》；"
            "③ 交房当天双方签《房屋交接单》。<br><br>"
            "若房东无正当理由克扣，可凭合同 + 转账记录向 12345 或住建委投诉。你在哪个城市、现在到哪个阶段了？"
        )
        return AnswerResult(
            mode="general",
            html=_t("租房知识 · 经验建议，各地执行有差异", "fa-book-open", "text-brand-600", body),
            followups=list(_FOLLOWUP),
        )

    # 默认：有上下文则总结上下文，否则通用引导
    if clauses:
        clause = sorted(clauses, key=lambda c: (c.clause_no is None, c.clause_no or 0))[0]
        citation = _citation(clause, contract_id)
        body = f"当前合同条款 {len(clauses)} 条，可问“物业费谁承担”“提前退租要付什么”“违约金怎么谈”。"
        if house is not None:
            rent = _field(house, "rent")
            deposit = _field(house, "deposit")
            commute = _field(house, "commute_min", "commuteMin")
            body = (
                f"当前房源 <b>{_field(house, 'no') or ''} {_field(house, 'name') or ''}</b>：月租 "
                f"{_money(rent) + ' 元' if rent is not None else '待确认'}，"
                f"{deposit or '押金待确认'}，通勤 {_minute_text(commute)}。<br>" + body
            )
        return AnswerResult(
            mode="context",
            html=_t("当前上下文", "fa-check-circle", "text-green-500", body),
            citations=[citation] if citation else [],
        )
    if house is not None:
        rent = _field(house, "rent")
        deposit = _field(house, "deposit")
        commute = _field(house, "commute_min", "commuteMin")
        body = (
            f"当前房源 <b>{_field(house, 'no') or ''} {_field(house, 'name') or ''}</b>：月租 "
            f"{_money(rent) + ' 元' if rent is not None else '待确认'}，{deposit or '押金待确认'}，"
            f"通勤 {str(commute) + ' 分钟' if commute is not None else '待确认'}。<br>"
            "尚未绑定合同，绑定后可逐项核验承诺与条款。"
        )
        return AnswerResult(
            mode="house_only",
            html=_t("当前上下文", "fa-check-circle", "text-green-500", body),
        )
    return AnswerResult(mode="general", html=KNOWLEDGE_HTML, followups=list(_FOLLOWUP))


# ============================ 推荐解释（确定性模板） ============================


def _house_values(
    house: Mapping[str, Any], prefs: Mapping[str, Any], item: Mapping[str, Any] | None
) -> ExplanationItem:
    item = item or {}
    rank = _field(item, "rank")
    monthly = _field(item, "monthly_cost", "monthlyCost")
    one_time = _field(item, "one_time_cost", "oneTimeCost")
    verdict = _field(item, "verdict")
    hard = list(_field(item, "hard_violations", "hardViolations") or [])
    hits = list(_field(item, "soft_hits", "softHits") or [])
    miss = list(_field(item, "soft_miss", "softMiss") or [])
    missing = list(_field(house, "missing") or [])
    verify = list(_field(house, "verify") or [])

    why: list[str] = []
    if rank is not None and monthly is not None and one_time is not None:
        why.append(f"排序第 {rank} 名：月成本约 {monthly} 元，一次性支出约 {one_time} 元。")
    if verdict:
        why.append(f"综合结论：{verdict}。")
    if hits:
        why.append(f"命中的偏好：{'、'.join(str(h) for h in hits)}。")

    tradeoffs: list[str] = []
    if miss:
        tradeoffs.append(f"未满足的偏好：{'、'.join(str(m) for m in miss)}。")
    if hard:
        tradeoffs.append(f"与硬约束冲突：{'、'.join(str(h) for h in hard)}，需先确认是否可接受。")
    if not tradeoffs:
        tradeoffs.append("当前没有明显的偏好取舍项。")

    risks = [f"待核验：{v}。" for v in verify[:3]]
    if hard:
        risks.append("硬约束未确认前不建议缴纳定金。")
    if not risks:
        risks.append("未上传合同，承诺条款尚未核验。")

    todos = [f"向房东/中介确认：{m}。" for m in missing[:4]]
    if not todos:
        todos.append("看房时核对家电状态并拍照留证。")

    prefs_commute = _field(prefs or {}, "commute")
    if prefs_commute is not None:
        todos.append(f"实地验证通勤是否接近 {prefs_commute} 分钟。")

    return ExplanationItem(
        why=why, tradeoffs=tradeoffs, risks=risks, todos=todos, next=["查看详情", "上传合同"]
    )


def mock_explain(
    houses: Sequence[Mapping[str, Any]],
    prefs: Mapping[str, Any],
    ranking_items: Mapping[str, Mapping[str, Any]],
) -> RecommendationExplanation:
    items: dict[str, ExplanationItem] = {}
    for house in houses:
        hid = str(_field(house, "id") or "")
        items[hid] = _house_values(house, prefs, ranking_items.get(hid))
    return RecommendationExplanation(items=items)


__all__ = [
    "FIELD_KEYWORDS",
    "KNOWLEDGE_HTML",
    "LAW_HTML",
    "LAW_SOURCES",
    "OOS_HTML",
    "match_clauses",
    "mock_answer",
    "mock_explain",
    "mock_extract_listings",
    "mock_judge",
]
