"""流程 A 收口：偏好版本与可解释推荐三视图（契约 §4.4 / §4.5）。

排名/成本由 services/domain.py 确定性计算；断言到具体顺序、硬约束与快照版本。
"""

from tests.conftest import add_house, recommend, wait_run


async def _three_houses(client, workspace) -> dict[str, str]:
    """A 贵但通勤短 / B 居中 / C 便宜但通勤长（用来区分 budget 与 commute 两个视图）。"""

    specs = {
        "A": {"rent": 6000, "commute_min": 20},
        "B": {"rent": 5000, "commute_min": 40},
        "C": {"rent": 4500, "commute_min": 55},
    }
    ids: dict[str, str] = {}
    for name, fields in specs.items():
        house = await add_house(
            client, workspace, name=f"房源{name}", deposit="押一付一", area=50, layout="一居", **fields
        )
        ids[name] = house["id"]
    return ids


async def test_preferences_version_increments(client, workspace):
    first = (await client.get(f"/api/v1/preferences?workspace_id={workspace}")).json()
    assert first["version"] == 1
    assert first["budget"] is None

    second = (await client.put(f"/api/v1/preferences?workspace_id={workspace}", json={"budget": 5500})).json()
    assert second["version"] == 2 and second["budget"] == 5500
    third = (await client.put(f"/api/v1/preferences?workspace_id={workspace}", json={"budget": 5000})).json()
    assert third["version"] == 3

    latest = (await client.get(f"/api/v1/preferences?workspace_id={workspace}")).json()
    assert latest["version"] == 3 and latest["budget"] == 5000


async def test_three_views_order_matches_domain_rules(client, workspace):
    ids = await _three_houses(client, workspace)
    await client.put(
        f"/api/v1/preferences?workspace_id={workspace}", json={"budget": 6000, "commute": 60}
    )
    result = await recommend(client, workspace)
    assert result["run"]["status"] == "done"
    rec = result["recommendation"]

    assert set(rec["views"]) == {"budget", "commute", "mix"}
    assert rec["views"]["budget"]["order"] == [ids["C"], ids["B"], ids["A"]]  # 月成本升序
    assert rec["views"]["commute"]["order"] == [ids["A"], ids["B"], ids["C"]]  # 通勤升序
    for view in ("budget", "commute", "mix"):
        items = rec["views"][view]["items"]
        assert sorted(item["rank"] for item in items.values()) == [1, 2, 3]
        assert items[ids["A"]]["monthly_cost"] == 6000
        assert items[ids["C"]]["monthly_cost"] == 4500

    assert {house["id"] for house in rec["snapshot"]["houses"]} == set(ids.values())
    assert rec["snapshot"]["prefs"]["version"] == 2


async def test_budget_change_updates_verdict(client, workspace):
    ids = await _three_houses(client, workspace)
    await client.put(f"/api/v1/preferences?workspace_id={workspace}", json={"budget": 6000, "commute": 60})
    before = await recommend(client, workspace)
    before_items = before["recommendation"]["views"]["mix"]["items"]
    assert before_items[ids["C"]]["verdict"] == "优先考虑"
    assert before_items[ids["A"]]["verdict"] == "可作为备选"

    await client.put(f"/api/v1/preferences?workspace_id={workspace}", json={"budget": 5900})
    after = await recommend(client, workspace)
    item = after["recommendation"]["views"]["mix"]["items"][ids["A"]]
    assert item["hard_violations"] and "预算" in item["hard_violations"][0]
    assert item["verdict"] == "不建议"
    assert after["recommendation"]["views"]["mix"]["order"][-1] == ids["A"]


async def test_commute_change_reorders_mix_view(client, workspace):
    ids = await _three_houses(client, workspace)
    await client.put(f"/api/v1/preferences?workspace_id={workspace}", json={"commute": 60})
    before = await recommend(client, workspace)
    assert before["recommendation"]["views"]["mix"]["order"] == [ids["C"], ids["B"], ids["A"]]

    await client.put(f"/api/v1/preferences?workspace_id={workspace}", json={"commute": 30})
    after = await recommend(client, workspace)
    order = after["recommendation"]["views"]["mix"]["order"]
    assert order != before["recommendation"]["views"]["mix"]["order"]
    assert order[0] == ids["A"]  # 只有 A 满足 30 分钟硬约束
    assert after["recommendation"]["views"]["mix"]["items"][ids["B"]]["hard_violations"]
    assert after["recommendation"]["views"]["mix"]["items"][ids["C"]]["hard_violations"]


async def test_snapshot_does_not_follow_new_preferences(client, workspace):
    ids = await _three_houses(client, workspace)
    first = await recommend(client, workspace)
    rec_id = first["recommendation"]["id"]
    assert first["recommendation"]["snapshot"]["prefs"]["version"] == 1
    first_order = first["recommendation"]["views"]["mix"]["order"]

    await client.put(
        f"/api/v1/preferences?workspace_id={workspace}", json={"budget": 4000, "commute": 10}
    )
    again = (await client.get(f"/api/v1/recommendations/{rec_id}")).json()
    assert again["prefs_version"] == 1
    assert again["snapshot"]["prefs"]["version"] == 1
    assert again["views"]["mix"]["order"] == first_order
    assert {house["id"] for house in again["snapshot"]["houses"]} == set(ids.values())


async def test_no_candidates_returns_no_drafts(client, workspace):
    resp = await client.post("/api/v1/recommendations", json={"workspace_id": workspace, "view": "mix"})
    assert resp.status_code == 202
    run = await wait_run(client, resp.json()["run_id"])
    assert run["status"] == "failed"
    assert run["error"]["code"] == "NO_DRAFTS"


async def test_about_window_flags_under_three_candidates(client, workspace):
    await add_house(client, workspace, name="房源一", rent=5000, commute_min=30, deposit="押一付一")
    await add_house(client, workspace, name="房源二", rent=4800, commute_min=35, deposit="押一付一")
    result = await recommend(client, workspace)
    window = result["run"]["result"]["about"]["window"]
    assert window["count"] == 2
    assert window["ok"] is False


async def test_explanation_and_about_are_keyed_by_house_id(client, workspace):
    """契约 §4.5：explanation 直接以 house_id 为键（不得多套一层 items），about 在 run result 与 GET 都可用。

    回归自 W4 报告缺陷 3：`_explanation_model` 曾把 `{"items": {...}}` 外层当成 house_id，
    导致前端 `explanation[house_id]` 取到 undefined、推荐卡五段全空。
    """

    ids = await _three_houses(client, workspace)
    await client.put(f"/api/v1/preferences?workspace_id={workspace}", json={"budget": 6000, "commute": 45})

    run = await recommend(client, workspace, view="mix")
    assert run["run"]["status"] == "done", run["run"]
    result = run["run"]["result"]
    assert set(result["explanation"]) == set(ids.values()), "run result 必须按 house_id 给出解释"
    assert "items" not in result["explanation"]
    top = result["explanation"][ids["A"]]
    assert top["why"] and isinstance(top["why"][0], str)
    assert set(top) >= {"why", "tradeoffs", "risks", "todos", "next"}
    assert result["about"]["hard_rules"] and result["about"]["window"]["count"] == 3

    fetched = run["recommendation"]
    assert set(fetched["explanation"]) == set(ids.values())
    assert fetched["explanation"][ids["A"]]["why"] == top["why"]
    assert fetched["about"]["hard_rules"] == result["about"]["hard_rules"]
    assert fetched["about"]["window"]["ok"] is True
