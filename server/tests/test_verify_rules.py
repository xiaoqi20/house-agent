"""房源承诺 × 合同条款核验测试（PRD §10 场景 2、契约 §4.7）。

场景 2：房源承诺「押一付一 / 允许养猫 / 物业费房东承担」对合同「押二付一 / 禁止养宠物 / 物业费由乙方承担」，
至少 3 个冲突项，每项都能回到条款（clause_id + 原文片段）并给出可执行建议；找不到条款的项目必须是「未约定」。
条款数据取自前端演示合同（`web/src/data/demo.ts` DEMO_CONTRACT_CLAUSES）。全部纯函数断言，不联网、不调用 LLM。
"""

from rentgraph.services.verify_rules import RESULTS, SEVERITY, VRow, compare_claims

CLAUSE_FIELDS = {
    "租金",
    "押金/付款方式",
    "物业费",
    "宠物",
    "可入住时间",
    "面积",
    "中介费",
    "网费/水电燃气",
    "租期",
    "转租",
    "合租/入住人数",
}


def house() -> dict:
    """场景 2 的目标房源（望京南湖东园一居，字段均已在确认面板确认）。"""
    return {
        "id": "h1",
        "no": "H1",
        "rent": 5800,
        "deposit": "押一付一",
        "propertyFee": 120,
        "propertyBear": "房东承担",
        "netFee": 0,
        "agencyFee": 0,
        "area": 68.5,
        "pet": "可养猫",
        "available": "10月1日可入住",
        "leaseReq": "一年",
        "sublet": "不可转租",
        "shared": False,
        "commuteMin": 35,
    }


def clauses() -> list[dict]:
    """合同条款（含 page/char_start 原文定位，与前端演示合同一致）。"""
    return [
        {
            "id": 2,
            "clause_no": 2,
            "title": "第二条 租赁房屋",
            "text": "甲方将位于北京市朝阳区望京南湖东园一区 3 号楼 1202 室出租给乙方居住使用，"
            "建筑面积 68.5 平方米。",
            "page": 1,
            "char_start": 120,
        },
        {
            "id": 3,
            "clause_no": 3,
            "title": "第三条 租赁期限",
            "text": "租赁期共 12 个月，自 2026 年 9 月 15 日起至 2027 年 9 月 14 日止。",
            "page": 1,
            "char_start": 160,
        },
        {
            "id": 4,
            "clause_no": 4,
            "title": "第四条 租金",
            "text": "月租金为人民币 6,000 元，乙方应于每期开始前 7 日支付。",
            "page": 2,
            "char_start": 200,
        },
        {
            "id": 5,
            "clause_no": 5,
            "title": "第五条 押金与支付",
            "text": "乙方按「押二付一」方式支付，签约当日支付押金人民币 12,000 元。",
            "page": 2,
            "char_start": 240,
        },
        {
            "id": 9,
            "clause_no": 9,
            "title": "第九条 物业费",
            "text": "租赁期内，该房屋物业费由乙方承担，随租金一并缴纳。",
            "page": 3,
            "char_start": 300,
        },
        {
            "id": 13,
            "clause_no": 13,
            "title": "第十三条 其他约定",
            "text": "租赁期内，乙方不得在房屋内饲养任何宠物；违反的，甲方有权解除合同并没收押金。",
            "page": 3,
            "char_start": 340,
        },
    ]


def rows_by_field(rows: list[VRow]) -> dict[str, VRow]:
    return {row.field: row for row in rows}


def result_counts(rows: list[VRow]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        counts[row.result] = counts.get(row.result, 0) + 1
    return counts


def row_of(house_overrides: dict, clauses_: list[dict], field: str) -> VRow:
    return rows_by_field(compare_claims({**house(), **house_overrides}, clauses_))[field]


# ---------- 场景 2 主链路 ----------


def test_scene2_conflicts_first_and_locate_clause() -> None:
    rows = compare_claims(house(), clauses())
    assert len(rows) == 11 and {row.field for row in rows} == CLAUSE_FIELDS
    assert result_counts(rows) == {"冲突": 5, "未约定": 4, "一致": 2}
    assert [row.result for row in rows[:5]] == ["冲突"] * 5
    assert all(row.result in RESULTS for row in rows)

    conflicts = [row for row in rows if row.result == "冲突"]
    assert len(conflicts) >= 3
    for row in conflicts:
        assert row.clause_id is not None and row.clause_text
        assert row.severity == "high"
        assert row.advice
    assert [row.field for row in rows[:5]] == ["租金", "押金/付款方式", "物业费", "宠物", "可入住时间"]

    rent = rows_by_field(rows)["租金"]
    assert (rent.clause_id, rent.page, rent.char_start) == (4, 2, 200)
    assert "6,000" in rent.clause_text and "5,800" in rent.advice
    assert "改回" in rent.advice and "写回一致版本" in rent.advice

    deposit = rows_by_field(rows)["押金/付款方式"]
    assert deposit.clause_id == 5 and "押二付一" in deposit.clause_text
    assert "押一付一" in deposit.advice and "多占用资金" in deposit.advice

    prop = rows_by_field(rows)["物业费"]
    assert prop.clause_id == 9 and "乙方承担" in prop.clause_text
    assert "物业费由房东承担" in prop.advice

    pet = rows_by_field(rows)["宠物"]
    assert pet.clause_id == 13 and "宠物" in pet.clause_text
    assert "要求删除禁止饲养条款" in pet.advice and "退租时恢复原状" in pet.advice

    available = rows_by_field(rows)["可入住时间"]
    assert available.clause_id == 3 and "2026 年 9 月 15 日" in available.clause_text
    assert "空置期" in available.advice


def test_scene2_unspecified_rows_reference_no_clause_and_ask_for_addendum() -> None:
    rows = compare_claims(house(), clauses())
    unspecified = [row for row in rows if row.result == "未约定"]
    assert {row.field for row in unspecified} == {"中介费", "网费/水电燃气", "转租", "合租/入住人数"}
    for row in unspecified:
        assert row.clause_id is None and row.clause_text == "未找到对应条款"
        assert (row.page, row.char_start) == (None, None)
        assert row.severity == "medium" and "补充协议" in row.advice


def test_scene2_consistent_rows_have_no_severity() -> None:
    rows = compare_claims(house(), clauses())
    consistent = [row for row in rows if row.result == "一致"]
    assert {row.field for row in consistent} == {"面积", "租期"}
    for row in consistent:
        assert row.severity is None and "按约履行" in row.advice


def test_rows_sorted_by_importance() -> None:
    order = {"冲突": 0, "未约定": 1, "无法判断": 2, "一致": 3}
    rows = compare_claims(house(), clauses())
    assert [order[row.result] for row in rows] == sorted(order[row.result] for row in rows)


def test_severity_table_matches_contract() -> None:
    assert SEVERITY == {"冲突": "high", "未约定": "medium", "无法判断": "low", "一致": None}


# ---------- 禁止推断为已承诺 ----------


def test_no_clause_never_infers_commitment() -> None:
    rows = compare_claims(house(), [])
    assert {row.result for row in rows} <= {"未约定", "无法判断"}
    assert "一致" not in {row.result for row in rows}
    pet = rows_by_field(rows)["宠物"]
    assert pet.result == "未约定" and pet.clause_id is None and "补充协议" in pet.advice


def test_missing_house_values_are_unknown_not_consistent() -> None:
    rows = compare_claims({}, clauses())
    assert {row.result for row in rows} == {"无法判断"}
    assert all(row.severity == "low" for row in rows)


def test_unparsable_clause_text_is_unknown() -> None:
    clause = {"id": 4, "clause_no": 4, "title": "第四条 租金", "text": "月租金按市场行情另行协商确定。"}
    assert row_of({}, [clause], "租金").result == "无法判断"
    vague_pet = {
        "id": 13,
        "clause_no": 13,
        "title": "第十三条 宠物",
        "text": "关于宠物饲养事宜由双方另行协商。",
    }
    assert row_of({}, [vague_pet], "宠物").result == "无法判断"


# ---------- 数值 / 日期 / 枚举判定 ----------


def test_rent_tolerance_is_zero() -> None:
    clause = [{"id": 4, "clause_no": 4, "title": "第四条 租金", "text": "月租金为人民币 6,000 元。"}]
    assert row_of({"rent": 6000}, clause, "租金").result == "一致"
    assert row_of({"rent": 5900}, clause, "租金").result == "冲突"


def test_deposit_amount_and_payment_pattern() -> None:
    clause = [
        {
            "id": 5,
            "clause_no": 5,
            "title": "第五条 押金与支付",
            "text": "乙方按「押一付一」方式支付，押金为人民币 5,800 元。",
        }
    ]
    assert row_of({}, clause, "押金/付款方式").result == "一致"
    wrong_amount = [
        {
            "id": 5,
            "clause_no": 5,
            "title": "第五条 押金与支付",
            "text": "乙方按「押一付一」方式支付，押金为人民币 12,000 元。",
        }
    ]
    conflict = row_of({}, wrong_amount, "押金/付款方式")
    assert conflict.result == "冲突" and "多占用资金" in conflict.advice


def test_property_fee_bearer_and_amount() -> None:
    bearer = [
        {
            "id": 9,
            "clause_no": 9,
            "title": "第九条 物业费",
            "text": "租赁期内，该房屋物业费由甲方承担，120 元/月。",
        }
    ]
    assert row_of({}, bearer, "物业费").result == "一致"
    amount = [
        {
            "id": 9,
            "clause_no": 9,
            "title": "第九条 物业费",
            "text": "租赁期内，该房屋物业费由甲方承担，200 元/月。",
        }
    ]
    assert row_of({}, amount, "物业费").result == "冲突"


def test_available_date_compared_by_day() -> None:
    assert row_of({"available": "2026年9月15日可入住"}, clauses(), "可入住时间").result == "一致"
    later = row_of({"available": "9月14日可入住"}, clauses(), "可入住时间")
    assert later.result == "冲突" and "晚于" in later.advice
    vague = row_of({"available": "随时可入住"}, clauses(), "可入住时间")
    assert vague.result == "无法判断"


def test_area_and_lease_months_and_agency_fee() -> None:
    assert row_of({}, clauses(), "面积").result == "一致"
    small = [{"id": 2, "clause_no": 2, "title": "第二条 租赁房屋", "text": "建筑面积 60 平方米。"}]
    assert row_of({}, small, "面积").result == "冲突"
    assert row_of({}, clauses(), "租期").result == "一致"
    assert row_of({"leaseReq": "6个月"}, clauses(), "租期").result == "冲突"
    fee = [{"id": 7, "clause_no": 7, "title": "第七条 中介费", "text": "中介服务费为 1,900 元，由乙方承担。"}]
    assert row_of({"agencyFee": 1900}, fee, "中介费").result == "一致"
    assert row_of({"agencyFee": 1900}, clauses(), "中介费").result == "未约定"


def test_utilities_amount_compared() -> None:
    clause = [{"id": 10, "clause_no": 10, "title": "第十条 其他费用", "text": "网费由乙方承担，50 元/月。"}]
    assert row_of({"netFee": 50}, clause, "网费/水电燃气").result == "一致"
    assert row_of({"netFee": 80}, clause, "网费/水电燃气").result == "冲突"


def test_sublet_and_shared_people_conflicts() -> None:
    sublet = [
        {
            "id": 11,
            "clause_no": 11,
            "title": "第十一条 转租",
            "text": "租赁期内乙方不得转租、分租或转借房屋。",
        }
    ]
    conflict = row_of({"sublet": "可转租"}, sublet, "转租")
    assert conflict.result == "冲突" and "经甲方书面同意可转租" in conflict.advice
    assert row_of({"sublet": "不可转租"}, sublet, "转租").result == "一致"
    people = [
        {"id": 12, "clause_no": 12, "title": "第十二条 居住人数", "text": "居住人数不得超过 1 人，不得合租。"}
    ]
    overshared = row_of({"shared": True, "maxPeople": 2}, people, "合租/入住人数")
    assert overshared.result == "冲突" and "禁止合租" in overshared.advice
    limit = [{"id": 12, "clause_no": 12, "title": "第十二条 居住人数", "text": "居住人数不得超过 1 人。"}]
    over_limit = row_of({"shared": False, "maxPeople": 2}, limit, "合租/入住人数")
    assert over_limit.result == "冲突" and "入住人数上限不一致" in over_limit.advice
    assert row_of({"shared": False, "maxPeople": 1}, limit, "合租/入住人数").result == "一致"


# ---------- 输入兼容 ----------


def test_orm_rows_and_frontend_triples_are_accepted() -> None:
    orm = [{"id": 4, "clause_no": 4, "raw_text": "月租金为人民币 6,000 元。", "page": 2, "char_start": 200}]
    triple = [[4, "第四条 租金", "月租金为人民币 6,000 元。"]]
    for clause_input in (orm, triple):
        row = compare_claims(house(), clause_input)
        rent = rows_by_field(row)["租金"]
        assert (rent.result, rent.clause_id, rent.clause_text) == ("冲突", 4, "月租金为人民币 6,000 元。")
    # 没有条款主键时回退条号（前端用条号定位合同原文）
    assert rows_by_field(compare_claims(house(), triple))["租金"].page is None
