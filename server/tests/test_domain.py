"""确定性领域核心测试：完整度 / 成本 / 硬约束 / 三视图排序（PRD §10 场景 1）。

场景 1 数据取自前端演示批次（`web/src/data/demo.ts` DEMO_BATCH_TEXT）：
低租金长通勤、较贵但通勤短、合租、信息缺失各一套，覆盖三视图排序与「允许合租」开关。
全部为纯函数断言，不联网、不调用 LLM。
"""

import pytest

from rentgraph.services.domain import (
    KEY_FIELDS,
    SOURCE_LABEL,
    DomainError,
    check_compare_window,
    comparison_missing_fields,
    completeness,
    hard_violations,
    is_filled,
    missing_fields,
    monthly_cost,
    normalise_house,
    one_time_cost,
    rank_views,
    soft_score,
    verdict,
)

PREFS = {
    "budget": 6000,
    "commute": 45,
    "needBathroom": True,
    "allowShared": False,
    "soft": {"south": False, "light": False, "highFloor": False, "bigArea": False, "flexPay": False},
}


def prefs(**overrides: object) -> dict:
    merged = {**PREFS, **overrides}
    merged["soft"] = {**PREFS["soft"], **(overrides.get("soft") or {})}
    return merged


def houses() -> list[dict]:
    """5 套候选：与 PRD §10 场景 1 的演示批次一致（合租 2 套、信息缺失 1 套）。"""
    return [
        {
            "id": "h1",
            "no": "H1",
            "status": "active",
            "source": "paste",
            "name": "望京南湖东园一居",
            "region": "朝阳·望京",
            "rent": 5800,
            "deposit": "押一付一",
            "propertyFee": 120,
            "propertyBear": "房东承担",
            "netFee": 0,
            "area": 68.5,
            "layout": "一居",
            "floor": "12/18层",
            "orientation": "南向",
            "bathroom": True,
            "lighting": "采光好",
            "commuteMin": 35,
            "available": "10月1日可入住",
            "pet": "可养猫",
        },
        {
            "id": "h2",
            "no": "H2",
            "status": "active",
            "source": "paste",
            "name": "酒仙桥将府家园开间",
            "region": "朝阳·酒仙桥",
            "rent": 4600,
            "deposit": "押一付一",
            "propertyFee": 80,
            "propertyBear": "租客承担",
            "netFee": 50,
            "area": 42,
            "layout": "开间",
            "floor": "3/6层",
            "orientation": "东向",
            "bathroom": True,
            "commuteMin": 42,
            "available": "随时可入住",
            "pet": "禁止宠物",
        },
        {
            "id": "h3",
            "no": "H3",
            "status": "active",
            "source": "paste",
            "name": "将台两居合租次卧",
            "region": "朝阳·将台",
            "rent": 3800,
            "deposit": "押一付三",
            "agencyFee": 1900,
            "area": 18,
            "layout": "两居合租次卧",
            "floor": "8/11层",
            "orientation": "北向",
            "bathroom": False,
            "commuteMin": 30,
            "shared": True,
            "maxPeople": 1,
        },
        {
            "id": "h4",
            "no": "H4",
            "status": "active",
            "source": "link",
            "name": "大望路现代城一居",
            "region": "朝阳·大望路",
            "rent": 6200,
            "layout": "一居",
            "orientation": "南向",
            "bathroom": True,
            "commuteMin": 22,
        },
        {
            "id": "h5",
            "no": "H5",
            "status": "active",
            "source": "manual",
            "name": "芍药居主卧带独卫",
            "region": "朝阳·芍药居",
            "rent": 4100,
            "deposit": "押一付一",
            "agencyFee": 0,
            "bathroom": True,
            "orientation": "北向",
            "commuteMin": 40,
            "shared": True,
            "pet": "可养猫",
        },
    ]


def order(items: list) -> list[str]:
    return [item.house_id for item in items]


def by_id(items: list) -> dict:
    return {item.house_id: item for item in items}


# ---------- 完整度 / 缺失 ----------


def test_key_fields_are_twelve_with_frontend_labels() -> None:
    assert len(KEY_FIELDS) == 12
    assert [label for _, label in KEY_FIELDS] == [
        "租金",
        "押金/付款方式",
        "物业费",
        "通勤",
        "户型",
        "面积",
        "楼层",
        "朝向",
        "独立卫浴",
        "可入住时间",
        "宠物",
        "区域",
    ]


def test_bathroom_false_counts_as_filled() -> None:
    assert is_filled({"bathroom": False}, "bathroom") is True
    assert is_filled({"bathroom": True}, "bathroom") is True
    assert is_filled({"bathroom": None}, "bathroom") is False


def test_completeness_and_missing_fields() -> None:
    assert completeness(houses()[0]) == 100  # 12/12 关键字段齐（含宠物）
    assert completeness(houses()[3]) == 50  # 6/12
    assert completeness({}) == 0
    no_pet = {key: value for key, value in houses()[0].items() if key != "pet"}
    assert completeness(no_pet) == 92
    assert missing_fields(no_pet) == ["宠物"]
    assert missing_fields(houses()[3]) == ["押金/付款方式", "物业费", "面积", "楼层", "可入住时间", "宠物"]


def test_comparison_missing_fields_gated_by_need_bathroom() -> None:
    assert comparison_missing_fields({"rent": None, "commuteMin": 30, "bathroom": True}, PREFS) == ["租金"]
    unknown_bathroom = {"rent": 5800, "commuteMin": 30, "bathroom": None}
    assert comparison_missing_fields(unknown_bathroom, PREFS) == ["独立卫浴"]
    assert comparison_missing_fields(unknown_bathroom, prefs(needBathroom=False)) == []


# ---------- 成本 ----------


def test_monthly_cost_counts_fixed_fees_and_flags_unknown() -> None:
    h1 = houses()[0]
    cost = monthly_cost(h1)
    assert (cost.sum, cost.unknown, cost.is_rent_missing) == (5920, [], False)
    h4 = monthly_cost(houses()[3])
    assert (h4.sum, h4.unknown, h4.is_rent_missing) == (6200, ["物业费", "网费"], False)
    missing_rent = monthly_cost({"propertyFee": 100})
    assert (missing_rent.sum, missing_rent.unknown) == (100, ["租金", "网费"])
    assert missing_rent.is_rent_missing is True


def test_one_time_cost_uses_deposit_months_before_pay_period() -> None:
    h1 = one_time_cost(houses()[0])
    assert (h1.deposit, h1.agency, h1.label) == (5800, None, "押一付一")
    # 前端只认「押X付」的 X：押一付三仍按 1 个月押金计算
    h3 = one_time_cost(houses()[2])
    assert (h3.deposit, h3.agency, h3.label) == (3800, 1900, "押一付三")
    unknown = one_time_cost({"rent": 5000, "deposit": ""})
    assert (unknown.deposit, unknown.label) == (0, "待确认")


# ---------- 硬约束 / 软偏好 ----------


def test_hard_violations_wording_matches_frontend() -> None:
    assert hard_violations(houses()[0], prefs(budget=5000)) == ["月租 5,800 超出预算 5,000"]
    assert hard_violations(houses()[2], PREFS) == ["无独立卫浴（硬约束不满足）"]
    assert hard_violations(houses()[3], PREFS) == ["月租 6,200 超出预算 6,000"]
    blanks = hard_violations({}, PREFS)
    assert blanks == [
        "月租缺失（关键硬约束无法验证，不可直接推荐）",
        "通勤时间缺失（关键硬约束无法验证，不可直接推荐）",
        "独立卫浴情况待确认（硬约束无法验证）",
    ]
    assert hard_violations(houses()[1], prefs(commute=30)) == ["通勤 42 分钟超出上限 30 分钟"]
    assert hard_violations(houses()[2], prefs(needBathroom=False)) == []


def test_soft_score_hits_and_miss() -> None:
    all_on = prefs(soft={"south": True, "light": True, "highFloor": True, "bigArea": True, "flexPay": True})
    score = soft_score(houses()[0], all_on)
    assert score.hits == ["南向", "采光好", "中高楼层", "面积 68.5㎡", "付款灵活"]
    assert (score.miss, score.score) == ([], 5)
    low = soft_score(houses()[1], all_on)
    assert low.hits == ["付款灵活"]
    assert low.miss == ["非南向", "采光未确认", "楼层偏低", "面积不大"]
    assert low.score == 1


def test_source_label_covers_frontend_sources() -> None:
    assert SOURCE_LABEL == {
        "paste": "用户粘贴",
        "manual": "手动填写",
        "batch": "批量粘贴",
        "file-xlsx": "Excel 导入",
        "file-docx": "Word 导入",
        "file-txt": "文本文件导入",
        "link": "外部链接",
    }


# ---------- 推荐状态 ----------


def test_verdict_mapping_derived_from_recommend_card() -> None:
    assert verdict(0, [], []) == "优先考虑"
    assert verdict(1, [], []) == "可作为备选"
    assert verdict(0, ["月租缺失…"], []) == "不建议"
    assert verdict(0, [], ["租金"]) == "可作为备选"  # 不可比不冒充「优先考虑」


# ---------- 三视图排序（PRD §10 场景 1） ----------


def test_scene1_mix_view_ranks_by_violations_then_cost() -> None:
    items = rank_views(houses(), PREFS, "mix")
    assert order(items) == ["h2", "h1", "h4", "h5", "h3"]  # 可比在前，违反硬约束/不可比在后
    assert [item.rank for item in items] == [1, 2, 3, 4, 5]
    assert by_id(items)["h2"].verdict == "优先考虑"
    assert by_id(items)["h1"].verdict == "可作为备选"
    assert by_id(items)["h4"].verdict == "不建议"
    assert by_id(items)["h3"].verdict == "不建议"  # 无独立卫浴（硬约束不满足）
    assert by_id(items)["h5"].comparable is False  # 未接受合租 → 不参与比较
    assert "不可比" in by_id(items)["h5"].tie_break_note
    assert by_id(items)["h2"].monthly_cost == 4730
    assert by_id(items)["h2"].one_time_cost == 4600
    assert all(item.tie_break_note for item in items)


def test_scene1_budget_view_and_commute_view() -> None:
    assert order(rank_views(houses(), PREFS, "budget")) == ["h2", "h1", "h4", "h3", "h5"]
    assert order(rank_views(houses(), PREFS, "commute")) == ["h4", "h1", "h2", "h3", "h5"]
    assert "月度成本最优" in rank_views(houses(), PREFS, "budget")[0].tie_break_note


def test_scene1_budget_change_flips_conclusion() -> None:
    tightened = rank_views(houses(), prefs(budget=5000), "mix")
    assert by_id(tightened)["h1"].verdict == "不建议"  # 5,800 > 5,000
    assert by_id(tightened)["h1"].hard_violations == ["月租 5,800 超出预算 5,000"]
    assert sum(1 for item in tightened if item.verdict == "不建议") == 3
    harsh = rank_views(houses(), prefs(budget=4500), "mix")
    assert not [item for item in harsh if item.verdict == "优先考虑"]  # 无一套满足预算
    assert by_id(harsh)["h2"].hard_violations == ["月租 4,600 超出预算 4,500"]


def test_scene1_commute_change_flips_order() -> None:
    base = order(rank_views(houses(), PREFS, "mix"))
    items = rank_views(houses(), prefs(commute=30), "mix")
    assert order(items) != base  # 通勤 30 分钟：h5 也变成硬约束不满足
    assert order(items) == ["h2", "h1", "h4", "h3", "h5"]
    assert by_id(items)["h1"].hard_violations == ["通勤 35 分钟超出上限 30 分钟"]
    assert by_id(items)["h5"].verdict == "不建议"
    relaxed = rank_views(houses(), prefs(commute=30, budget=6500), "mix")
    assert order(relaxed)[:3] == ["h4", "h2", "h1"]  # 通勤 22 分钟的 h4 成为唯一达标项
    assert by_id(relaxed)["h4"].verdict == "优先考虑"


def test_scene1_shared_houses_join_comparison_only_when_allowed() -> None:
    locked = rank_views(houses(), PREFS, "mix")
    assert [item.house_id for item in locked if item.comparable] == ["h2", "h1", "h4"]
    opened = rank_views(houses(), prefs(allowShared=True), "mix")
    assert [item.house_id for item in opened if item.comparable] == ["h5", "h2", "h1", "h3", "h4"]
    assert by_id(opened)["h3"].comparable is True
    assert by_id(opened)["h5"].verdict == "优先考虑"
    assert order(opened)[0] == "h5"  # 合租 4,100 元/月 且无违反项


def test_scene1_soft_prefs_change_ranking() -> None:
    soft_on = prefs(soft={"south": True, "light": True, "highFloor": True, "bigArea": True, "flexPay": True})
    items = rank_views(houses(), soft_on, "mix")
    assert order(items)[0] == "h1"  # 命中 5 项软偏好，压过更便宜但只命中 1 项的 h2
    assert by_id(items)["h1"].soft_hits == ["南向", "采光好", "中高楼层", "面积 68.5㎡", "付款灵活"]


# ---------- 其它约束 ----------


def test_snake_case_and_object_inputs_normalise_to_same_result() -> None:
    snake = normalise_house(
        {
            "property_fee": 120,
            "commute_min": 35,
            "agency_fee": 0,
            "net_fee": 0,
            "property_bear": "房东承担",
            "rent": 5800,
            "bathroom": True,
        }
    )
    assert snake["propertyFee"] == 120 and snake["commuteMin"] == 35 and snake["agencyFee"] == 0
    assert monthly_cost(snake).sum == 5920
    assert hard_violations(snake, PREFS) == []

    class OrmRow:
        rent = 6200
        commute_min = 22
        bathroom = True
        property_fee = None
        net_fee = None

    assert monthly_cost(OrmRow()).sum == 6200
    assert hard_violations(OrmRow(), PREFS) == ["月租 6,200 超出预算 6,000"]


def test_dropped_houses_are_excluded_from_ranking_and_window() -> None:
    dropped = {"id": "h9", "no": "H9", "status": "dropped", "rent": 3000, "commuteMin": 10, "bathroom": True}
    pool = houses() + [dropped]
    assert "h9" not in order(rank_views(pool, PREFS, "mix"))
    assert check_compare_window(pool)["count"] == 5


def test_check_compare_window_boundaries() -> None:
    two = check_compare_window(houses()[:2])
    assert (two["count"], two["ok"]) == (2, False)
    assert "少于 3 套" in two["message"]
    three = check_compare_window(houses()[:3])
    assert (three["count"], three["ok"]) == (3, True)
    assert "3—10" in three["message"]
    ten = check_compare_window([{**houses()[0], "id": f"x{i}"} for i in range(10)])
    assert (ten["count"], ten["ok"]) == (10, True)
    eleven = check_compare_window([{**houses()[0], "id": f"y{i}"} for i in range(11)])
    assert (eleven["count"], eleven["ok"]) == (11, False)
    assert "超过 10 套" in eleven["message"]


def test_unknown_view_raises_typed_error() -> None:
    with pytest.raises(DomainError) as excinfo:
        rank_views(houses(), PREFS, "cheapest")
    assert excinfo.value.code == "DOMAIN_UNKNOWN_VIEW"
