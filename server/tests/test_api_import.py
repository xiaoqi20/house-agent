"""流程 A：房源导入 API（契约 §4.2）：批量/粘贴/文件 → 字段草稿 → 确认入库。

LLM_PROVIDER=mock，全部离线确定性。断言到真实字段值（租金/通勤/证据/缺失），
不允许只断言 200；未确认的 drafts 必须不进入推荐。
"""

import pytest

from rentgraph.config import settings
from tests.conftest import (
    SAMPLES,
    add_house,
    collect_events,
    confirm_batch,
    import_batch,
    upload_batch,
    wait_run,
)

BATCH_TEXT = (SAMPLES / "houses.txt").read_text()
RENTS = [5800, 5200, 3200, 6300]
TWO_HOUSES_TEXT = (
    "1. 望京花园 2室1厅 60平 月租 5800 元，押一付三\n"
    "2. 望京西园三区 1室1厅 48平 月租 5200 元，押一付一"
)


async def test_paste_batch_streams_to_done_with_real_drafts(client, workspace):
    resp = await client.post(
        "/api/v1/import-batches",
        json={"workspace_id": workspace, "source": "batch", "text": BATCH_TEXT},
    )
    assert resp.status_code == 202, resp.text
    batch_id = resp.json()["id"]
    run_id = resp.json()["run_id"]

    events = await collect_events(client, run_id)
    assert [event["type"] for event in events][-1] == "done"
    assert all(event["run_id"] == run_id for event in events)
    result = events[-1]["data"]["result"]
    assert len(result["drafts"]) == 4

    batch = (await client.get(f"/api/v1/import-batches/{batch_id}")).json()
    assert batch["status"] == "ready"
    assert batch["house_count"] == 4
    assert [draft["rent"] for draft in batch["drafts"]] == RENTS
    first = batch["drafts"][0]
    assert first["name"].startswith("望京花园")
    assert first["deposit"] == "押一付三"
    assert first["evidence"]["rent"].replace(" ", "") == "5800元"  # 证据逐字来自原文
    assert "地址" in first["missing"]  # 未提取到的字段必须标记，不得用 0/"" 冒充


async def test_unconfirmed_drafts_do_not_enter_recommendation(client, workspace):
    await import_batch(client, workspace, BATCH_TEXT)
    assert (await client.get(f"/api/v1/houses?workspace_id={workspace}")).json() == []

    resp = await client.post("/api/v1/recommendations", json={"workspace_id": workspace, "view": "mix"})
    run = await wait_run(client, resp.json()["run_id"])
    assert run["status"] == "failed"
    assert run["error"]["code"] == "NO_DRAFTS"


async def test_confirm_persists_houses_with_continuous_numbers_and_duplicate_hint(client, workspace):
    batch = await import_batch(client, workspace, BATCH_TEXT)
    resp = await confirm_batch(client, batch)
    assert resp.status_code == 200, resp.text
    assert [house["no"] for house in resp.json()["houses"]] == ["H1", "H2", "H3", "H4"]
    assert [house["rent"] for house in resp.json()["houses"]] == RENTS

    stored = (await client.get(f"/api/v1/houses?workspace_id={workspace}")).json()
    assert [house["no"] for house in stored] == ["H1", "H2", "H3", "H4"]

    again = await import_batch(client, workspace, BATCH_TEXT)
    existing_ids = {house["id"] for house in stored}
    assert all(draft["duplicate_of"] in existing_ids for draft in again["drafts"])
    resp2 = await confirm_batch(client, again)
    assert resp2.status_code == 200, resp2.text
    assert "疑似重复" in resp2.json()["hint"]
    assert [house["no"] for house in resp2.json()["houses"]] == ["H5", "H6", "H7", "H8"]


async def test_reconfirm_same_batch_rejected(client, workspace):
    batch = await import_batch(client, workspace, BATCH_TEXT)
    assert (await confirm_batch(client, batch)).status_code == 200
    resp = await confirm_batch(client, batch)
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "INVALID_STATE"


async def test_confirm_below_three_hints_window(client, workspace):
    batch = await import_batch(client, workspace, TWO_HOUSES_TEXT)
    assert len(batch["drafts"]) == 2
    resp = await confirm_batch(client, batch)
    assert resp.status_code == 200, resp.text
    assert "少于 3" in resp.json()["hint"]


async def test_confirm_over_ten_houses_rejected(client, workspace):
    for index in range(10):
        await add_house(client, workspace, name=f"手动{index}", rent=5000, commute_min=30)
    batch = await import_batch(client, workspace, BATCH_TEXT)
    resp = await confirm_batch(client, batch, houses=batch["drafts"][:1])
    assert resp.status_code == 422, resp.text
    assert resp.json()["error"]["code"] == "TOO_MANY_HOUSES"


@pytest.mark.parametrize(
    ("filename", "rents", "commutes"),
    [
        ("houses.txt", RENTS, None),
        ("houses.xlsx", RENTS, [35, 28, 12, 55]),
        ("houses.csv", RENTS, [35, 28, 12, 55]),
        ("houses.md", RENTS, None),
    ],
)
async def test_file_upload_parses_real_drafts(client, workspace, filename, rents, commutes):
    batch = await upload_batch(client, workspace, filename, (SAMPLES / filename).read_bytes())
    assert batch["status"] == "ready"
    assert [draft["rent"] for draft in batch["drafts"]] == rents
    assert all(draft["name"] for draft in batch["drafts"])
    assert all(draft["evidence"] for draft in batch["drafts"])
    if commutes:
        assert [draft["commute_min"] for draft in batch["drafts"]] == commutes


async def test_upload_unsupported_format_rejected(client, workspace):
    resp = await client.post(
        "/api/v1/import-batches/upload",
        data={"workspace_id": workspace},
        files={"file": ("deck.pptx", b"not a house file")},
    )
    assert resp.status_code == 415, resp.text
    assert resp.json()["error"]["code"] == "UNSUPPORTED_FORMAT"
    assert "xlsx" in resp.json()["error"]["hint"]


async def test_upload_over_size_limit_rejected(client, workspace, monkeypatch):
    monkeypatch.setattr(settings, "max_upload_mb", 0)  # 0MB 上限：任何非空文件都超限
    resp = await client.post(
        "/api/v1/import-batches/upload",
        data={"workspace_id": workspace},
        files={"file": ("houses.txt", (SAMPLES / "houses.txt").read_bytes())},
    )
    assert resp.status_code == 409, resp.text
    assert resp.json()["error"]["code"] == "INVALID_STATE"
