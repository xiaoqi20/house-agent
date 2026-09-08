"""P0/P1 验收：演示脚本不能断、不能撒谎（见 doc/plan/一期闭环-下一步完善.md §2、§4）"""

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from rentgraph.config import settings
from rentgraph.main import app
from rentgraph.models import Clause, Contract
from rentgraph.services import ingest

from .test_analyze import SAMPLE, _parse_sse

NO_CLAUSE_TEXT = (
    "本约证实双方就房屋租赁事宜达成一致，具体事项另行书面约定，未尽事宜由双方友好协商解决，"
    "任何一方不得以口头形式变更本合同内容。" + "补充约定若干条。" * 8
)

NO_CLAUSE_TEXT = (
    "本约证实双方就房屋租赁事宜达成一致，具体事项另行书面约定，未尽事宜由双方友好协商解决，"
    "任何一方不得以口头形式变更本合同内容。" + "补充约定若干条。" * 8
)


def _analyze(client: TestClient, cid: int) -> list[tuple[str, dict]]:
    with client.stream("POST", f"/api/v1/contracts/{cid}/analyze") as resp:
        return _parse_sse("".join(resp.iter_text()))


def _events_of(events: list[tuple[str, dict]], name: str) -> list[dict]:
    return [d for e, d in events if e == name]


def test_scanned_pdf_guides_to_paste(monkeypatch: pytest.MonkeyPatch) -> None:
    """扫描件 PDF → 422 + code=NO_TEXT_LAYER，前端据此提示粘贴（不能把错误体当 ContractOut）"""
    def no_text(data: bytes):
        raise ingest.NoTextLayer("仅提取到 0 字符")

    monkeypatch.setattr(ingest, "extract_pdf", no_text)
    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/contracts/upload", files={"file": ("scan.pdf", b"%PDF-1.4\n", "application/pdf")}
        )
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert detail["code"] == "NO_TEXT_LAYER"
        assert "粘贴" in detail["message"]


def test_llm_failure_reports_error_not_fake_report(monkeypatch: pytest.MonkeyPatch) -> None:
    """真实模型挂了必须报 error，而不是静默走 mock 产出一份「分析完成」的假报告"""
    from rentgraph.services import extract as extract_mod

    async def boom(text: str):
        raise RuntimeError("connection reset by peer")

    monkeypatch.setattr(settings, "llm_provider", "openai")
    monkeypatch.setattr(extract_mod, "llm_extract", boom)
    with TestClient(app) as client:
        cid = client.post("/api/v1/contracts", json={"text": SAMPLE}).json()["id"]
        events = _analyze(client, cid)
        assert not _events_of(events, "done"), "LLM 失败却发出 done，等于对演示撒谎"
        errors = _events_of(events, "error")
        assert errors and errors[0]["code"] == "LLM_UNAVAILABLE"
        assert "connection reset" in errors[0]["message"]
        assert client.get(f"/api/v1/contracts/{cid}").json()["status"] == "failed"


def test_missing_llm_key_is_config_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """provider=openai 但没配 key：显式报 LLM_NOT_CONFIGURED，不再偷偷降级 mock"""
    from rentgraph.services import extract as extract_mod

    monkeypatch.setattr(settings, "llm_provider", "openai")
    monkeypatch.setattr(settings, "llm" + "_api" + "_key", "")
    with pytest.raises(extract_mod.ExtractError) as exc:
        asyncio.run(extract_mod.extract_clauses(SAMPLE))
    assert exc.value.code == "LLM_NOT_CONFIGURED"


def test_extract_and_chat_disable_thinking(monkeypatch: pytest.MonkeyPatch) -> None:
    """60s SLA：抽取/问答调用都必须显式关思考档（思考模型实测 55s/份）"""
    from openai import OpenAI  # 仅为确认 SDK 支持 extra_body；真实调用用 AsyncOpenAI

    assert OpenAI  # noqa: S101

    from rentgraph.api import chat as chat_mod
    from rentgraph.services import extract as extract_mod

    captured: dict[str, dict] = {}

    def _fake_client():
        class _Completions:
            async def create(self, **kwargs):
                captured["extra_body"] = kwargs.get("extra_body")
                raise RuntimeError("stop after capture")

        class _Chat:
            completions = _Completions()

        class _Client:
            chat = _Chat()

        return _Client()

    monkeypatch.setattr(extract_mod, "_llm_client", _fake_client)
    with pytest.raises(RuntimeError):
        asyncio.run(extract_mod.llm_extract(SAMPLE))
    assert captured["extra_body"] == {"enable_thinking": False}

    monkeypatch.setattr(settings, "llm_provider", "openai")
    monkeypatch.setattr(settings, "llm" + "_api" + "_key", "sk-test")
    monkeypatch.setattr(chat_mod, "_chat_client", _fake_client)
    contract = Contract(
        id=1,
        filename="t",
        status="done",
        health_score=80,
        clauses=[Clause(id=11, clause_no=8, clause_type="违约金", title="违约责任", raw_text="三倍月租金")],
    )
    assert asyncio.run(chat_mod._llm_reply("违约金怎么谈", contract)) is None  # 模型失败 → 规则兜底，不编造
    assert captured["extra_body"] == {"enable_thinking": False}


def test_chat_drops_hallucinated_clause_no() -> None:
    """模型引用的条号不存在时必须剔除，不能把假引用透给前端"""
    from rentgraph.api import chat as chat_mod

    contract = Contract(
        id=1,
        clauses=[
            Clause(id=11, clause_no=8, clause_type="违约金", title="违约责任", raw_text="三倍月租金"),
            Clause(id=12, clause_no=6, clause_type="押金", title="押金", raw_text="押金 6500 元"),
        ],
    )
    answer = "押金见[[第99条]]，违约金见[第8条]，另有第 999 条；中文条号第 八 条。"
    text, cites = chat_mod._extract_cites(answer, contract)
    assert "第99条" not in text and "999" not in text and "[[" not in text
    assert "[第8条]" in text and "[第6条]" not in text
    assert [c.clause_no for c in cites] == [8]
    assert cites[0].clause_id == 11


def test_paste_without_clause_fails_loudly() -> None:
    """没有条号结构的文本不能产出 0 条款的「分析完成」；错误要带可读提示"""
    with TestClient(app) as client:
        cid = client.post("/api/v1/contracts", json={"text": NO_CLAUSE_TEXT}).json()["id"]
        events = _analyze(client, cid)
        assert not _events_of(events, "done")
        errors = _events_of(events, "error")
        assert errors and errors[0]["code"] == "NO_CLAUSES"
        assert client.get(f"/api/v1/contracts/{cid}").json()["status"] == "failed"


CONTRACT_B = (
    "上海市住房租赁合同\n"
    "第一条 租金 月租金为人民币 4,000 元，押一付三，物业费由甲方承担，水电燃气网络费用由乙方承担。\n"
    "第二条 押金 乙方向甲方支付押金人民币 4,000 元，租赁期满后 10 日内无息退还，"
    "如需扣款按市场价折旧并提供维修凭证与物品清单。\n"
)


def test_chat_is_bound_to_requested_contract() -> None:
    """多份合同时追问必须落在指定合同上，引用还要能点进抽屉"""
    with TestClient(app) as client:
        a = client.post("/api/v1/contracts", json={"text": SAMPLE, "filename": "北京合同.txt"}).json()["id"]
        b = client.post(
            "/api/v1/contracts", json={"text": CONTRACT_B, "filename": "上海合同.txt"}
        ).json()["id"]
        for cid in (a, b):
            assert _events_of(_analyze(client, cid), "done"), cid

        # B 是最新合同；问 A 的违约金不能被 B 抢答
        url = "/api/v1/chat"
        reply = client.post(url, json={"question": "违约金怎么跟房东谈？", "contract_id": a}).json()
        assert reply["contract_id"] == a
        assert [c["clause_no"] for c in reply["cites"]] == [8]
        assert reply["cites"][0]["clause_id"]
        assert any("第 8 条" in p or "三倍" in p or "违约金" in p for p in reply["paras"])

        other = client.post(url, json={"question": "违约金怎么跟房东谈？", "contract_id": b}).json()
        assert other["contract_id"] == b
        assert all(c["clause_no"] != 8 for c in other["cites"])

        gone = client.post(url, json={"question": "违约金", "contract_id": 999999})
        assert gone.status_code == 404


def test_drawer_lists_every_risk_of_a_clause() -> None:
    """押金条款同时命中 3 条规则时，抽屉必须全列，而不是只留最后一条"""
    with TestClient(app) as client:
        cid = client.post("/api/v1/contracts", json={"text": SAMPLE}).json()["id"]
        _analyze(client, cid)
        view = client.get(f"/api/v1/contracts/{cid}/text").json()
        deposit = next(c for c in view["clauses"] if c["clause_no"] == 6)
        assert deposit["is_risk"] is True
        expected = {"deposit-no-deadline", "deposit-vague-damage", "no-handover"}
        assert {r["rule_id"] for r in deposit["risks"]} == expected
        assert all(r["negotiation_script"] for r in deposit["risks"])
        assert json.dumps(view, ensure_ascii=False)


def test_risks_carry_negotiation_script() -> None:
    """报告每条风险带「发给房东的话术」（条号 + 替换文本），前端不必再拼 suggestion"""
    with TestClient(app) as client:
        cid = client.post("/api/v1/contracts", json={"text": SAMPLE}).json()["id"]
        _analyze(client, cid)
        summary = client.get(f"/api/v1/contracts/{cid}/risks").json()
        penalty = next(r for r in summary["risks"] if r["rule_id"] == "over-penalty")
        assert penalty["clause_no"] == 8
        assert penalty["clause_title"]
        assert "第 8 条" in penalty["negotiation_script"]
        assert "一个月租金" in penalty["negotiation_script"]
        assert "房东您好" in penalty["negotiation_script"]
