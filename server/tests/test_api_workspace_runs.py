"""工作台生命周期与统一运行接口（契约 §4.1 / §2.1）。

覆盖：到期 410、未知 404、取消运行后不再有终态写入、SSE 分帧与终态结束重放。
"""

import asyncio

import pytest

from rentgraph.services import engine
from tests.conftest import (
    SAMPLES,
    collect_events,
    create_workspace,
    expire_workspace,
    wait_run,
)

BATCH_TEXT = (SAMPLES / "houses.txt").read_text()


async def test_expired_workspace_returns_410(client, workspace):
    await expire_workspace(workspace)
    resp = await client.get(f"/api/v1/houses?workspace_id={workspace}")
    assert resp.status_code == 410, resp.text
    assert resp.json()["error"]["code"] == "WORKSPACE_EXPIRED"


async def test_unknown_workspace_returns_404(client):
    resp = await client.get("/api/v1/houses?workspace_id=不存在")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "WORKSPACE_NOT_FOUND"
    assert (await client.get("/api/v1/workspaces/不存在")).status_code == 404


async def test_get_unknown_run_returns_404(client):
    resp = await client.get("/api/v1/runs/不存在")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


async def test_cancel_run_stops_without_done(client, workspace, monkeypatch):
    original = engine.extract_listings

    async def slow(text: str, source: str):
        await asyncio.sleep(5)
        return await original(text, source)

    monkeypatch.setattr(engine, "extract_listings", slow)
    posted = await client.post(
        "/api/v1/import-batches",
        json={"workspace_id": workspace, "source": "batch", "text": BATCH_TEXT},
    )
    run_id = posted.json()["run_id"]
    await asyncio.sleep(0.05)

    cancelled = await client.post(f"/api/v1/runs/{run_id}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert (await wait_run(client, run_id))["status"] == "cancelled"

    events = await collect_events(client, run_id)
    types = [event["type"] for event in events]
    assert types[-1] == "cancelled"
    assert "done" not in types  # 取消后不得再写入终态结果


async def test_sse_frames_and_finishes_on_terminal(client, workspace):
    posted = await client.post(
        "/api/v1/import-batches",
        json={"workspace_id": workspace, "source": "batch", "text": BATCH_TEXT},
    )
    run_id = posted.json()["run_id"]
    events = await collect_events(client, run_id)

    assert events
    for event in events:
        assert event["run_id"] == run_id
        assert {"event_id", "run_id", "seq", "type", "data"} <= set(event)
    assert [event["seq"] for event in events] == sorted(event["seq"] for event in events)
    assert events[-1]["type"] == "done"
    assert len(events[-1]["data"]["result"]["drafts"]) == 4


async def test_sse_replays_finished_run(client, workspace):
    posted = await client.post(
        "/api/v1/import-batches",
        json={"workspace_id": workspace, "source": "batch", "text": BATCH_TEXT},
    )
    run_id = posted.json()["run_id"]
    await wait_run(client, run_id)

    events = await collect_events(client, run_id)
    assert events[-1]["type"] == "done"
    assert events[-1]["data"]["result"]["house_count"] == 4


@pytest.mark.parametrize("path", ["/api/v1/runs/不存在/events"])
async def test_unknown_run_events_returns_404(client, path):
    resp = await client.get(path)
    assert resp.status_code == 404


async def test_new_workspace_is_isolated(client):
    first = await create_workspace(client)
    second = await create_workspace(client)
    assert first != second
    assert (await client.get(f"/api/v1/houses?workspace_id={first}")).json() == []
