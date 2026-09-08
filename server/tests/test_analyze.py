import json

from fastapi.testclient import TestClient

from rentgraph.main import app

SAMPLE = (
    "北京市房屋租赁合同\n"
    "第一条 租赁房屋 甲方将位于北京市朝阳区望京街道某小区 3 号楼 1202 室房屋出租给乙方居住使用，建筑面积 68.5 平方米。\n"
    "第三条 租赁期限 租赁期共 12 个月，自 2026 年 9 月 15 日起至 2027 年 9 月 14 日止。\n"
    "第四条 租金 月租金为人民币 6,500 元，按押一付三方式支付，乙方应于每期开始前 7 日支付。\n"
    "第六条 押金 乙方于签约当日支付房屋租赁押金人民币 6,500 元。租赁期满，房屋及设施无损坏的，甲方退还押金。\n"
    "第八条 违约责任 任何一方违约的，应向守约方支付违约金，违约金金额为月租金的三倍，并赔偿由此造成的全部损失。\n"
    "第十条 房屋维修 租赁期内，因乙方使用不当造成的房屋及设施损坏，由乙方负责维修或赔偿。\n"
    "第十二条 续租 租赁期届满前 30 日内乙方未书面通知甲方不续租的，视为自动续租一年，续租期间租金在上一年度基础上上浮 5%。"
)


def _parse_sse(body: str) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    name = None
    for line in body.splitlines():
        if line.startswith("event:"):
            name = line.split(":", 1)[1].strip()
        elif line.startswith("data:") and name:
            events.append((name, json.loads(line.split(":", 1)[1].strip())))
            name = None
    return events


def test_full_analyze_chain() -> None:
    with TestClient(app) as client:
        created = client.post("/api/v1/contracts", json={"text": SAMPLE, "filename": "测试合同.txt"})
        assert created.status_code == 201, created.text
        cid = created.json()["id"]

        with client.stream("POST", f"/api/v1/contracts/{cid}/analyze") as resp:
            assert resp.status_code == 200
            body = "".join(resp.iter_text())

        events = _parse_sse(body)
        progress = [d for e, d in events if e == "progress"]
        done = [d for e, d in events if e == "done"]
        assert progress and progress[0]["status"] == "active"
        assert done, f"no done event; body={body[:500]}"
        assert done[0]["clause_count"] == 7
        assert done[0]["risk_count"] >= 3

        risks = client.get(f"/api/v1/contracts/{cid}/risks").json()
        assert risks["counts"]["high"] >= 3
        assert risks["health_score"] == 100 - 12 * risks["counts"]["high"] - 6 * risks["counts"]["medium"] - 3 * risks["counts"]["low"]
        rule_ids = {r["rule_id"] for r in risks["risks"]}
        assert {"over-penalty", "deposit-no-deadline", "auto-renewal"} <= rule_ids
        assert all(r["clause_no"] for r in risks["risks"])  # grounding 到条号

        text_view = client.get(f"/api/v1/contracts/{cid}/text").json()
        assert text_view["contract_id"] == cid
        assert any(c["is_risk"] for c in text_view["clauses"])
