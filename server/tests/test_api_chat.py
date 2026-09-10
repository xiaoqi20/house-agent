"""流程 C：上下文问答 API（契约 §4.8、PRD §5）。

断言引用存在性校验、无上下文降级、移除上下文后不再声称「你的合同」、
超范围与法规来源/免责、以及消息持久化。
"""

from tests.conftest import add_house, ask, collect_events, create_contract, create_conversation

SAMPLE_CONTRACT = (
    "北京市房屋租赁合同\n"
    "第一条 当事人：出租方（甲方）王某，承租方（乙方）张三。\n"
    "第二条 租赁房屋：甲方将位于北京市朝阳区望京南湖东园一区 3 号楼 1202 室出租给乙方居住使用，"
    "建筑面积 68.5 平方米。\n"
    "第三条 租赁期限：共 12 个月，自 2026 年 9 月 15 日起至 2027 年 9 月 14 日止。\n"
    "第四条 租金：月租金为人民币 6,000 元，乙方应于每期开始前 7 日支付。\n"
    "第五条 押金与支付：乙方按「押二付一」方式支付，签约当日支付押金人民币 12,000 元。\n"
    "第六条 水电燃气费用：租赁期内水、电、燃气费用由乙方按实际使用量承担。\n"
    "第八条 违约责任：任何一方违约，应向守约方支付违约金，金额为月租金的三倍。\n"
    "第九条 物业费：租赁期内，该房屋物业费由乙方承担，随租金一并缴纳。\n"
    "第十条 房屋维修：因乙方使用不当造成设施损坏由乙方负责维修。\n"
    "第十三条 其他约定：租赁期内乙方不得在房屋内饲养任何宠物；违反的，甲方有权解除合同。"
)


async def _context(client, workspace) -> dict:
    house = await add_house(
        client, workspace, name="望京一居", rent=5800, property_bear="房东承担", property_fee=120
    )
    contract = await create_contract(client, workspace, SAMPLE_CONTRACT)
    conversation = await create_conversation(client, workspace)
    return {"house": house, "contract": contract, "conversation": conversation}


async def test_context_question_cites_existing_clause(client, workspace):
    context = await _context(client, workspace)
    result = await ask(
        client,
        context["conversation"],
        "物业费谁承担？",
        house_id=context["house"]["id"],
        contract_id=context["contract"]["contract_id"],
    )
    answer = result["run"]["result"]
    assert answer["mode"] == "context"
    assert answer["citations"]
    clause_nos = {entry[0] for entry in context["contract"]["run"]["result"]["clauses_list"]}
    for citation in answer["citations"]:
        assert citation["clause_no"] in clause_nos
    assert answer["citations"][0]["clause_no"] == 9
    assert "第 9 条" in answer["html"]

    messages = (await client.get(f"/api/v1/conversations/{context['conversation']}/messages")).json()
    assert [message["role"] for message in messages] == ["user", "ai"]
    ai = messages[1]
    assert ai["id"] == answer["message_id"]
    assert ai["content"]["mode"] == "context"
    assert ai["content"]["html"]
    assert ai["citations"][0]["clause_no"] == 9  # 消息持久化带引用


async def test_hallucinated_citation_is_stripped(client, workspace, monkeypatch):
    from rentgraph.services.llm import answer as answer_mod
    from rentgraph.services.llm.models import AnswerResult, Citation

    def fake_answer(question, house, clauses, contract_id):
        return AnswerResult(
            mode="context",
            html="<p>根据你的合同第 99 条，押金应当退还。</p>",
            citations=[Citation(clause_no=99, label="第 99 条")],
        )

    monkeypatch.setattr(answer_mod, "mock_answer", fake_answer)
    context = await _context(client, workspace)
    result = await ask(
        client,
        context["conversation"],
        "押金怎么退？",
        house_id=context["house"]["id"],
        contract_id=context["contract"]["contract_id"],
    )
    answer = result["run"]["result"]
    assert answer["citations"] == []
    assert answer["mode"] != "context"  # 引用被剔除后必须降级措辞
    assert "第 99 条" not in answer["html"]
    assert "相关条款" in answer["html"]
    assert "以合同原文为准" in answer["html"]


async def test_no_context_returns_general(client, workspace):
    conversation = await create_conversation(client, workspace)
    result = await ask(client, conversation, "物业费谁承担？")
    answer = result["run"]["result"]
    assert answer["mode"] == "general"
    assert answer["citations"] == []


async def test_removing_contract_stops_referencing_your_contract(client, workspace):
    context = await _context(client, workspace)
    first = await ask(
        client,
        context["conversation"],
        "物业费谁承担？",
        house_id=context["house"]["id"],
        contract_id=context["contract"]["contract_id"],
    )
    assert first["run"]["result"]["mode"] == "context"

    assert (
        await client.delete(f"/api/v1/contracts/{context['contract']['contract_id']}")
    ).status_code == 204
    second = await ask(client, context["conversation"], "物业费谁承担？", house_id=context["house"]["id"])
    answer = second["run"]["result"]
    assert answer["mode"] == "house_only"
    assert answer["citations"] == []
    assert "你的合同" not in answer["html"]


async def test_price_question_is_out_of_scope(client, workspace):
    conversation = await create_conversation(client, workspace)
    result = await ask(client, conversation, "这套房明年房价会涨吗？")
    answer = result["run"]["result"]
    assert answer["mode"] == "out_of_scope"
    assert "超出当前能力范围" in answer["html"]


async def test_law_question_returns_sources_and_disclaimer(client, workspace):
    conversation = await create_conversation(client, workspace)
    result = await ask(client, conversation, "租房押金有什么法律规定？")
    answer = result["run"]["result"]
    assert answer["sources"]
    assert "不构成法律结论" in answer["html"]


async def test_answer_streams_incremental_tokens(client, workspace):
    """PRD §9.2：回答必须流式产出（逐段 token），而不是算完整段一次性灌进去。

    契约：token 事件的 text 依次追加；done.result.html 必须与流式内容一致（不得是第二份答案）。
    """

    conversation = await create_conversation(client, workspace)
    house = await add_house(client, workspace, name="望京南湖东园一居", rent=5800, deposit="押一付一")
    created = await ask(client, conversation, "物业费谁承担？", house_id=house["id"])
    events = await collect_events(client, created["run_id"])

    tokens = [event for event in events if event["type"] == "token"]
    assert len(tokens) >= 3, f"应分多片推送，实际 {len(tokens)} 片"
    assert [event["seq"] for event in tokens] == sorted(event["seq"] for event in tokens), "token 顺序必须递增"

    streamed = "".join(event["data"]["text"] for event in tokens)
    terminal = events[-1]
    assert terminal["type"] == "done"
    answer = terminal["data"]["result"]
    assert answer["html"], "终结结果必须带 html"
    assert streamed.strip() == answer["html"].strip(), "流式内容与终结 html 必须一致（否则用户会看到两份答案）"
