"""流程 B 输入：合同解析 API（契约 §4.6）。

覆盖：条款条号/原文定位、风险规则命中与 health_score、重新解析幂等、
过短 / 图片 OCR / 无文字层 PDF 的明确错误码、原始文件字节回读、上传白名单与大小限制。
"""

from rentgraph.config import settings
from tests.conftest import SAMPLES, create_contract, upload_contract, wait_run

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
CLAUSE_NOS = [1, 2, 3, 4, 5, 6, 8, 9, 10, 13]
_LEVEL_DEDUCTION = {"high": 12, "medium": 6, "low": 3}


async def test_paste_contract_clauses_carry_numbers_and_spans(client, workspace):
    created = await create_contract(client, workspace, SAMPLE_CONTRACT)
    assert created["run"]["status"] == "done", created["run"].get("error")

    view = (await client.get(f"/api/v1/contracts/{created['contract_id']}/text")).json()
    assert [clause["clause_no"] for clause in view["clauses"]] == CLAUSE_NOS
    for clause in view["clauses"]:
        assert clause["raw_text"]
        assert clause["char_start"] is not None and clause["char_end"] is not None
        assert clause["char_end"] > clause["char_start"]
        assert clause["page"] is None  # 粘贴文本没有分页信息，不伪造页码

    risky = next(clause for clause in view["clauses"] if clause["clause_no"] == 8)
    assert risky["is_risk"] is True
    assert risky["risks"]
    assert all("第 8 条" in risk["negotiation_script"] for risk in risky["risks"])


async def test_risk_rules_and_health_score_and_negotiation(client, workspace):
    created = await create_contract(client, workspace, SAMPLE_CONTRACT)
    detail = (await client.get(f"/api/v1/contracts/{created['contract_id']}")).json()
    view = (await client.get(f"/api/v1/contracts/{created['contract_id']}/text")).json()

    levels = [risk["level"] for clause in view["clauses"] for risk in clause["risks"]]
    assert "high" in levels  # 违约金三倍命中 over-penalty
    expected = max(0, 100 - sum(_LEVEL_DEDUCTION[level] for level in levels))
    assert detail["health_score"] == expected < 100
    assert "第 8 条" in detail["negotiation"]
    assert "一个月租金" in detail["negotiation"]  # 谈判话术带条号与建议替换文本


async def test_reparse_is_idempotent(client, workspace):
    created = await create_contract(client, workspace, SAMPLE_CONTRACT)
    before = (await client.get(f"/api/v1/contracts/{created['contract_id']}/text")).json()
    detail_before = (await client.get(f"/api/v1/contracts/{created['contract_id']}")).json()

    retry = await client.post(f"/api/v1/contracts/{created['contract_id']}/retry")
    assert retry.status_code == 202
    run = await wait_run(client, retry.json()["run_id"])
    assert run["status"] == "done"

    after = (await client.get(f"/api/v1/contracts/{created['contract_id']}/text")).json()
    detail_after = (await client.get(f"/api/v1/contracts/{created['contract_id']}")).json()
    assert [clause["clause_no"] for clause in after["clauses"]] == CLAUSE_NOS
    assert len(after["clauses"]) == len(before["clauses"])
    assert detail_after["health_score"] == detail_before["health_score"]
    assert _count_risks(after) == _count_risks(before)


def _count_risks(view: dict) -> int:
    return sum(len(clause["risks"]) for clause in view["clauses"])


async def test_pasted_contract_file_endpoint_has_no_original(client, workspace):
    created = await create_contract(client, workspace, SAMPLE_CONTRACT)
    resp = await client.get(f"/api/v1/contracts/{created['contract_id']}/file")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


async def test_text_too_short_rejected(client, workspace):
    resp = await client.post("/api/v1/contracts", json={"workspace_id": workspace, "text": "太短了"})
    assert resp.status_code == 400, resp.text
    error = resp.json()["error"]
    assert error["code"] == "TEXT_TOO_SHORT"
    assert "粘贴" in error["hint"]


async def test_image_upload_returns_ocr_unsupported_and_status_failed(client, workspace):
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 32
    created = await upload_contract(client, workspace, "房东拍的条款.png", png)
    assert created["run"]["status"] == "failed"
    assert created["run"]["error"]["code"] == "OCR_UNSUPPORTED"
    detail = (await client.get(f"/api/v1/contracts/{created['contract_id']}")).json()
    assert detail["status"] == "failed"
    assert detail["reason"]


async def test_scanned_pdf_returns_no_text_layer(client, workspace):
    created = await upload_contract(client, workspace, "scanned.pdf", (SAMPLES / "scanned.pdf").read_bytes())
    assert created["run"]["status"] == "failed"
    error = created["run"]["error"]
    assert error["code"] == "NO_TEXT_LAYER"
    assert "粘贴" in error["hint"]
    assert "字符" in error["hint"]  # 字符数写进 hint，前端据此提示粘贴
    detail = (await client.get(f"/api/v1/contracts/{created['contract_id']}")).json()
    assert detail["status"] == "failed"


async def test_uploaded_pdf_serves_bytes_and_page_positions(client, workspace):
    raw = (SAMPLES / "contract.pdf").read_bytes()
    created = await upload_contract(client, workspace, "contract.pdf", raw)
    assert created["run"]["status"] == "done"

    got = await client.get(f"/api/v1/contracts/{created['contract_id']}/file")
    assert got.status_code == 200
    assert got.content == raw

    view = (await client.get(f"/api/v1/contracts/{created['contract_id']}/text")).json()
    assert view["clauses"]
    for clause in view["clauses"]:
        assert clause["page"] in {1, 2}
        assert clause["char_start"] is not None and clause["char_end"] > clause["char_start"]


async def test_unsupported_doc_upload_rejected(client, workspace):
    resp = await client.post(
        "/api/v1/contracts/upload",
        data={"workspace_id": workspace},
        files={"file": ("合同.doc", b"\xd0\xcf\x11\xe0binary")},
    )
    assert resp.status_code == 415, resp.text
    error = resp.json()["error"]
    assert error["code"] in {"UNSUPPORTED_FORMAT", "DOC_UNSUPPORTED"}
    assert "docx" in error["hint"]


async def test_upload_over_size_limit_rejected(client, workspace, monkeypatch):
    monkeypatch.setattr(settings, "max_upload_mb", 0)
    resp = await client.post(
        "/api/v1/contracts/upload",
        data={"workspace_id": workspace},
        files={"file": ("contract.pdf", (SAMPLES / "contract.pdf").read_bytes())},
    )
    assert resp.status_code == 409, resp.text
    assert resp.json()["error"]["code"] == "INVALID_STATE"
