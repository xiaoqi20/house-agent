"""流程 B：房源承诺 × 合同条款核验 API（契约 §4.7、PRD §10 场景 2）。

场景 2：房源「押一付一 / 允许养猫 / 物业费房东承担」对合同「押二付一 / 禁宠 / 物业费乙方」。
断言 ≥3 冲突且每项可回到条款原文；未匹配项必须是「未约定」且 clause_no 为空；话术带条号。
"""

from tests.conftest import add_house, create_contract, create_verification

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


async def _verified(client, workspace) -> dict:
    house = await add_house(
        client,
        workspace,
        name="望京南湖东园一居",
        rent=5800,
        deposit="押一付一",
        property_bear="房东承担",
        property_fee=120,
        pet="可养猫",
        area=68.5,
        commute_min=35,
    )
    contract = await create_contract(client, workspace, SAMPLE_CONTRACT)
    return await create_verification(client, workspace, house["id"], contract["contract_id"])


async def test_scene2_conflicts_locate_clause_and_no_inference(client, workspace):
    result = await _verified(client, workspace)
    assert result["run"]["status"] == "done"
    out = result["verification"]
    items = out["items"]

    conflicts = [item for item in items if item["result"] == "冲突"]
    assert len(conflicts) >= 3
    assert {"租金", "押金/付款方式", "物业费", "宠物"} <= {item["field"] for item in conflicts}
    for item in conflicts:
        assert item["clause_no"] is not None
        assert item["clause_text"]
        assert item["advice"]
        assert item["char_start"] is not None  # 可回到合同原文定位

    unspecified = [item for item in items if item["result"] == "未约定"]
    assert unspecified
    for item in unspecified:
        assert item["clause_no"] is None  # 未匹配到条款不得推断为已承诺

    assert out["summary"]["冲突"] >= 3
    assert {"物业费", "押金/付款方式"} <= set(out["summary"]["high_priority"])


async def test_scene2_items_carry_anchor_and_negotiation_has_clause_numbers(client, workspace):
    result = await _verified(client, workspace)
    items = {item["field"]: item for item in result["verification"]["items"]}
    assert items["租金"]["anchor"] == "hd-rent"
    assert items["物业费"]["anchor"] == "hd-property"

    negotiation = result["verification"]["negotiation"]
    assert "建议与房东确认" in negotiation
    assert "第 13 条" in negotiation  # 宠物冲突
    assert "第 5 条" in negotiation  # 押金/付款方式冲突


async def test_verification_requires_house_and_contract(client, workspace):
    resp = await client.post(
        "/api/v1/verifications",
        json={"workspace_id": workspace, "house_id": "缺失", "contract_id": "缺失"},
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["error"]["code"] == "CONTEXT_MISSING"


async def test_unknown_verification_returns_404(client):
    resp = await client.get("/api/v1/verifications/不存在")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"
