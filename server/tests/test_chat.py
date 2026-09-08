import json

from fastapi.testclient import TestClient

from rentgraph.main import app

from .test_analyze import SAMPLE


def test_chat_rule_based() -> None:
    with TestClient(app) as client:
        cid = client.post("/api/v1/contracts", json={"text": SAMPLE}).json()["id"]
        with client.stream("POST", f"/api/v1/contracts/{cid}/analyze"):
            pass

        reply = client.post("/api/v1/chat", json={"question": "违约金条款怎么跟房东谈？", "contract_id": cid}).json()
        assert "第 8 条" in reply["cite"]
        assert [c["clause_no"] for c in reply["cites"]] == [8]
        assert reply["contract_id"] == cid
        assert any("违约金" in p for p in reply["paras"])
        # 第 6 步演示脚本要求"引用第 8 条原文"：答案里必须带真实条款原文，而不是只有建议
        assert any("第八条" in p or "三倍" in p for p in reply["paras"])

        reply = client.post("/api/v1/chat", json={"question": "押金不退怎么办？", "contract_id": cid}).json()
        assert "第 6 条" in reply["cite"]

        reply = client.post("/api/v1/chat", json={"question": "整体怎么样？", "contract_id": cid}).json()
        assert reply["cites"] == []
        assert json.dumps(reply, ensure_ascii=False)
