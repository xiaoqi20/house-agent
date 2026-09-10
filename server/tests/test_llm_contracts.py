"""LLM 契约层（W1/Lane C）：结构化输出 + mock 确定性实现 + 后置校验。

离线、确定性（LLM_PROVIDER=mock 由 conftest 设置）。覆盖：
1. 房源抽取的字段级 grounding（与前端 parseHousesInput 的演示值一致）
2. 幻觉条款被 grounding 丢弃并计入 dropped
3. 引用的存在性校验与语气降级、法规来源、超范围分支
4. 未匹配到条款必须「未约定」
5. 推荐解释的数字后置校验
"""

import pytest

from rentgraph.config import settings
from rentgraph.services.llm import (
    AnswerResult,
    Citation,
    ClauseData,
    LLMError,
    answer_question,
    explain_recommendation,
    extract_clauses,
    extract_listings,
    ground_numbers,
    guard_citations,
    judge_promise,
    norm_text,
)
from rentgraph.services.llm import contracts as contracts_mod

# 与 web/src/data/demo.ts 的 DEMO_BATCH_TEXT 逐字一致（原型演示粘贴内容）；拆分仅为守住行宽
DEMO_BATCH_TEXT = (
    "① 望京南湖东园一居 整租 5800/月 押一付一 68.5平 12/18层 南向 独立卫浴 采光好 "
    "地铁14号线望京站350米 通勤35分钟 物业费房东承担 允许养猫 10月1日可入住 家具家电齐全\n"
    "② 酒仙桥将府家园开间 整租 4600/月 押一付一 42平 3/6层 东向 独立卫浴 "
    "地铁14号线将台站 通勤42分钟 网费50/月 随时可入住 禁止养宠物\n"
    "③ 将台两居合租次卧 3800/月 押一付三 18平 8/11层 北向 无独卫 地铁30分钟 中介费半个月租金 限住1人\n"
    "④ 大望路现代城一居 整租 6200/月 独立卫浴 通勤22分钟 南向 来自链家链接 押金和物业费待与中介确认\n"
    "⑤ 芍药居主卧带独卫 合租 4100/月 押一付一 独立卫浴 通勤40分钟 北向 可养猫 房东直租无中介费"
)

CONTRACT_TEXT = """北京市房屋租赁合同
第一条 当事人：出租方（甲方）王某，承租方（乙方）张三。
第二条 租赁房屋：甲方将位于北京市朝阳区望京南湖东园一区 3 号楼 1202 室出租给乙方，建筑面积 68.5 平方米。
第三条 租赁期限：共 12 个月，自 2026 年 9 月 15 日起至 2027 年 9 月 14 日止。
第四条 租金：月租金为人民币 6,000 元，乙方应于每期开始前 7 日支付。
第五条 押金与支付：乙方按押二付一方式支付，签约当日支付押金 12,000 元。
第六条 水电燃气费用：租赁期内水、电、燃气费用由乙方按实际使用量承担。
第八条 违约责任：任何一方违约，应向守约方支付违约金，金额为月租金的三倍。
第九条 物业费：租赁期内物业费由乙方承担。
第十三条 其他约定：租赁期内乙方不得在房屋内饲养任何宠物。"""

# 分页文本：第 1—4 条在第 1 页，第 5 条起在第 2 页（用于校验 page 与 char 偏移）
CONTRACT_PAGES = [
    "北京市房屋租赁合同\n第一条 当事人：出租方（甲方）王某，承租方（乙方）张三。\n"
    "第二条 租赁房屋：甲方将位于北京市朝阳区望京南湖东园一区 3 号楼 1202 室出租给乙方，"
    "建筑面积 68.5 平方米。\n"
    "第三条 租赁期限：共 12 个月，自 2026 年 9 月 15 日起至 2027 年 9 月 14 日止。\n"
    "第四条 租金：月租金为人民币 6,000 元，乙方应于每期开始前 7 日支付。\n",
    "第五条 押金与支付：乙方按押二付一方式支付，签约当日支付押金 12,000 元。\n"
    "第六条 水电燃气费用：租赁期内水、电、燃气费用由乙方按实际使用量承担。\n"
    "第八条 违约责任：任何一方违约，应向守约方支付违约金，金额为月租金的三倍。\n"
    "第九条 物业费：租赁期内物业费由乙方承担。\n"
    "第十三条 其他约定：租赁期内乙方不得在房屋内饲养任何宠物。\n",
]

CONTRACT_CLAUSE_NOS = [1, 2, 3, 4, 5, 6, 8, 9, 13]  # 9 条中文合同的抽样

HOUSE = {
    "id": "h1",
    "no": "H1",
    "name": "望京南湖东园一居",
    "rent": 5800,
    "deposit": "押一付一",
    "property_fee": 120,
    "property_bear": "房东承担",
    "commute_min": 35,
}


async def _clauses() -> list[ClauseData]:
    return (await extract_clauses(CONTRACT_TEXT, CONTRACT_PAGES)).clauses


# ---------------------------------- 1. 房源抽取 ----------------------------------


async def test_extract_listings_demo_batch_matches_frontend_values() -> None:
    result = await extract_listings(DEMO_BATCH_TEXT, "batch")

    assert len(result.drafts) == 5
    assert result.truncated == 0
    assert [d.rent for d in result.drafts] == [5800, 4600, 3800, 6200, 4100]
    first = result.drafts[0]
    assert (first.name, first.area, first.commute_min, first.floor) == (
        "望京南湖东园一居 整租",
        68.5,
        35,
        "12/18层",
    )
    assert (first.orientation, first.layout, first.bathroom, first.shared) == ("南向", "一居", True, False)
    assert (first.pet, first.property_bear, first.metro) == ("允许宠物", "房东承担", "14号线望京站")
    # 原型此处拼出「10月1日可可入住」（重复字），后端按同样口径去掉重复；第 2 条与 enrichDemo 覆盖值一致
    assert first.available == "10月1日可入住"
    assert result.drafts[1].available == "随时可入住"
    assert result.drafts[2].bathroom is False and result.drafts[2].shared is True


async def test_extract_listings_caps_at_ten_and_reports_truncation() -> None:
    """契约 §4.2 上限 10 套：超出部分截断，但要显式上报，不静默丢弃"""
    line = "整租 5000/月 押一付一 40平 3/6层 南向 独立卫浴 通勤30分钟"
    result = await extract_listings("\n".join(f"{i}. 房源{i} {line}" for i in range(1, 13)), "batch")

    assert len(result.drafts) == 10
    assert result.truncated == 2


async def test_extract_listings_evidence_is_locatable() -> None:
    """每个提取到的字段都要有能在原文定位的 evidence（字段级防幻觉）"""
    compact = norm_text(DEMO_BATCH_TEXT)
    result = await extract_listings(DEMO_BATCH_TEXT, "batch")

    for draft in result.drafts:
        for field, snippet in draft.evidence.items():
            assert norm_text(snippet) in compact, f"{field} 证据无法定位：{snippet!r}"


async def test_extract_listings_missing_fields_stay_null() -> None:
    """第 4 条写着「押金和物业费待与中介确认」：押金必须为 null 且列入 missing"""
    drafts = (await extract_listings(DEMO_BATCH_TEXT, "batch")).drafts
    fourth = drafts[3]

    assert fourth.deposit is None
    assert "押金/付款方式" in fourth.missing
    assert "deposit" not in fourth.evidence


async def test_extract_listings_drops_ungrounded_field(monkeypatch: pytest.MonkeyPatch) -> None:
    """模型编造的字段（带假证据）必须被丢弃：值置 null + 计入 missing"""
    from rentgraph.services.llm import listing as listing_mod
    from rentgraph.services.llm import mock as mock_mod

    original = mock_mod.mock_extract_listings

    def fake(text: str, source: str):
        extraction = original(text, source)
        extraction.drafts[0].rent = 9999
        extraction.drafts[0].evidence["rent"] = "租金 9999 元"
        return extraction

    monkeypatch.setattr(listing_mod, "mock_extract_listings", fake)
    drafts = (await extract_listings(DEMO_BATCH_TEXT, "batch")).drafts

    assert drafts[0].rent is None
    assert "租金" in drafts[0].missing


# ---------------------------------- 2. 条款抽取 ----------------------------------


async def test_extract_clauses_spans_and_pages() -> None:
    result = await extract_clauses(CONTRACT_TEXT, CONTRACT_PAGES)
    clauses = result.clauses

    assert result.dropped == 0
    assert [c.clause_no for c in clauses] == CONTRACT_CLAUSE_NOS
    assert clauses[0].title == "第一条 当事人"
    assert clauses[-1].title == "第十三条 其他约定"
    full = norm_text(CONTRACT_TEXT)
    for c in clauses:
        assert c.char_start is not None and c.char_end is not None
        assert full[c.char_start : c.char_end] == norm_text(c.text)
    assert [c.page for c in clauses] == [1, 1, 1, 1, 2, 2, 2, 2, 2]
    by_no = {c.clause_no: c for c in clauses}
    assert (by_no[3].date_from, by_no[3].date_to) == ("2026-09-15", "2027-09-14")
    assert by_no[8].clause_type == "违约金" and by_no[8].months == 3
    assert "物业费" in by_no[9].text


async def test_extract_clauses_drops_hallucinated_clause(monkeypatch: pytest.MonkeyPatch) -> None:
    """把「第 9 条」原文改写成合同里没有的句子：必须被 grounding 丢弃并计入 dropped"""
    original = contracts_mod.mock_extract

    def fake(text: str) -> list[ClauseData]:
        hallucinated = ClauseData(
            clause_no=9,
            clause_type="其他",
            title="第九条 物业费",
            text="第九条 物业费：租赁期内物业费由甲方承担并出具发票。",
        )
        return [*original(text), hallucinated]

    monkeypatch.setattr(contracts_mod, "mock_extract", fake)
    result = await extract_clauses(CONTRACT_TEXT, CONTRACT_PAGES)

    assert result.dropped == 1
    assert [c.clause_no for c in result.clauses] == CONTRACT_CLAUSE_NOS
    assert all("出具发票" not in c.text for c in result.clauses)


async def test_extract_clauses_without_any_clause_raises() -> None:
    with pytest.raises(LLMError) as exc:
        await extract_clauses("本约证实双方就房屋租赁事宜达成一致，具体事项另行书面约定。")
    assert exc.value.code == "NO_CLAUSES"


# ---------------------------------- 3. 上下文问答 ----------------------------------


async def test_answer_with_contract_and_house_cites_existing_clause() -> None:
    clauses = await _clauses()
    result = await answer_question("物业费谁承担", HOUSE, clauses, "c1")

    assert result.mode == "context"
    assert result.citations, "有物业费条款时必须给出引用"
    citation = result.citations[0]
    assert citation.clause_no == 9
    assert citation.clause_no in {c.clause_no for c in clauses}
    assert citation.page == 2 and citation.char_start is not None and citation.char_end is not None
    assert "<script" not in result.html.lower()


async def test_answer_early_termination_cites_existing_clause() -> None:
    clauses = await _clauses()
    result = await answer_question("提前退租要付什么", HOUSE, clauses, "c1")

    assert result.mode == "context"
    assert [c.clause_no for c in result.citations] == [8]


async def test_answer_drops_missing_clause_reference() -> None:
    """条款集合里没有物业费条款：不得引用第 9 条，语气降级为通用建议"""
    clauses = [c for c in await _clauses() if c.clause_no != 9]
    result = await answer_question("物业费谁承担", HOUSE, clauses, "c1")

    assert result.mode != "context"
    assert result.citations == []
    assert "根据你的合同" not in result.html


def test_guard_citations_drops_unknown_and_degrades_mode() -> None:
    constructed = AnswerResult(
        mode="context",
        html='<p class="font-medium text-gray-900">结合你的合同 · 引用 第 9 条</p><p>物业费由乙方承担。</p>',
        citations=[
            Citation(clause_no=9, label="第 9 条", page=2, char_start=10, char_end=30),
            Citation(clause_no=4, label="第 4 条", page=1, char_start=1, char_end=9),
        ],
    )
    clauses = [ClauseData(clause_no=4, title="第四条 租金", text="月租金为 6,000 元。")]
    guarded = guard_citations(constructed, clauses)

    assert guarded.mode == "general"
    assert [c.clause_no for c in guarded.citations] == [4]
    assert "第 9 条" not in guarded.html and "相关条款" in guarded.html


async def test_answer_without_context_is_general() -> None:
    result = await answer_question("物业费谁承担", None, [], None)

    assert result.mode == "general"
    assert result.citations == []
    assert "城市" in result.html


async def test_answer_price_prediction_is_out_of_scope() -> None:
    result = await answer_question("房价会涨吗", HOUSE, await _clauses(), "c1")

    assert result.mode == "out_of_scope"
    assert result.citations == []


async def test_answer_law_question_has_sources_and_disclaimer() -> None:
    result = await answer_question("民法典怎么规定", None, [], None)

    assert result.mode == "general"
    assert any("flk.npc.gov.cn" in s for s in result.sources)
    assert "不构成法律结论" in result.html


async def test_answer_escapes_user_controllable_html() -> None:
    """房源字段（用户可控）进 html 前必须转义：白名单净化不允许脚本/图片标签"""
    house = {**HOUSE, "name": '<img src=x onerror="alert(1)">', "deposit": "<script>alert(1)</script>"}
    result = await answer_question("这个房源怎么样", house, await _clauses(), "c1")

    assert "&lt;img" in result.html and "&lt;script" in result.html
    assert "<img" not in result.html and "<script" not in result.html
    assert 'class="fas fa-check-circle' in result.html  # 图标 class 保留，不被净化误删


# ---------------------------------- 4. 承诺核验 ----------------------------------


async def test_judge_promise_without_matching_clause_is_unspecified() -> None:
    clauses = await _clauses()
    judgement = await judge_promise("房东口头承诺维修由房东负责", "维修", clauses)

    assert judgement.result == "未约定"
    assert judgement.clause_no is None
    assert judgement.result != "一致"


async def test_judge_promise_detects_conflict() -> None:
    clauses = await _clauses()
    judgement = await judge_promise("月租 5,800 元", "租金", clauses)

    assert judgement.result == "冲突"
    assert judgement.clause_no == 4
    assert "6,000" in judgement.reason or "6000" in judgement.reason


async def test_judge_promise_matches_written_promise() -> None:
    clauses = await _clauses()
    judgement = await judge_promise("押金 12,000 元", "押金/付款方式", clauses)

    assert judgement.result == "一致"
    assert judgement.clause_no == 5


# ---------------------------------- 5. 推荐解释 ----------------------------------

HOUSES = [
    {
        "id": "h1",
        "no": "H1",
        "name": "望京南湖东园一居",
        "rent": 5800,
        "missing": ["物业费承担方"],
        "verify": [],
    },
    {
        "id": "h2",
        "no": "H2",
        "name": "大望路现代城一居",
        "rent": 6200,
        "missing": [],
        "verify": ["押金方式待确认"],
    },
]
PREFS = {"budget": 6000, "commute": 40}
RANKING = {
    "h1": {
        "rank": 1,
        "monthly_cost": 5920,
        "one_time_cost": 11600,
        "hard_violations": [],
        "soft_hits": ["南向"],
        "soft_miss": ["采光"],
        "verdict": "优先考虑",
    },
    "h2": {
        "rank": 2,
        "monthly_cost": 6320,
        "one_time_cost": 12400,
        "hard_violations": [],
        "soft_hits": [],
        "soft_miss": ["通勤"],
        "verdict": "可考虑",
    },
}


def test_ground_numbers_drops_uncomputable_amount() -> None:
    assert ground_numbers("月成本约 5920 元，一次性支出约 11600 元。", [5920, 11600]) is not None
    assert ground_numbers("月租 7,900 元，明显更便宜。", [5920, 11600]) is None


async def test_explain_recommendation_five_segments() -> None:
    result = await explain_recommendation(HOUSES, PREFS, RANKING)
    item = result.items["h1"]

    assert item.why and item.tradeoffs and item.risks and item.todos and item.next
    assert "5920" in " ".join(item.why)


async def test_explain_recommendation_grounds_numbers(monkeypatch: pytest.MonkeyPatch) -> None:
    """解释里出现计算结果之外的金额 → 该句被剔除"""
    from rentgraph.services.llm import explain as explain_mod
    from rentgraph.services.llm import mock as mock_mod

    original = mock_mod.mock_explain

    def fake(houses, prefs, ranking_items):
        result = original(houses, prefs, ranking_items)
        result.items["h1"].why.append("改造后每月可省 500 元。")
        return result

    monkeypatch.setattr(explain_mod, "mock_explain", fake)
    result = await explain_recommendation(HOUSES, PREFS, RANKING)
    text = " ".join(result.items["h1"].why)

    assert "500" not in text
    assert "5920" in text


# ---------------------------------- 6. provider 选择 ----------------------------------


async def test_unknown_provider_never_falls_back_to_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "llm_provider", "gemini")

    with pytest.raises(LLMError) as exc:
        await extract_listings(DEMO_BATCH_TEXT, "batch")
    assert exc.value.code == "LLM_PROVIDER_UNKNOWN"

    with pytest.raises(LLMError) as exc2:
        await extract_clauses(CONTRACT_TEXT)
    assert exc2.value.code == "LLM_PROVIDER_UNKNOWN"
