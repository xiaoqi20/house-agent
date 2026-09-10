"""API 层测试夹具：契约 §6 分层测试的第 4/5 层（离线、确定性）。

在任何 rentgraph 模块 import 之前用环境变量把 DATABASE_URL 指向临时 SQLite，
LLM_PROVIDER 固定 mock，UPLOAD_DIR 指向临时目录，保证测试不碰仓库数据、不访问网络。
每个用例一份干净的表结构；用例结束取消残留后台运行并释放连接池（避免跨用例事件循环复用）。
"""

import asyncio
import contextlib
import os
import shutil
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="rentgraph-test-"))
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TMP / 'test.db'}"
os.environ["LLM_PROVIDER"] = "mock"
os.environ["UPLOAD_DIR"] = str(_TMP / "uploads")

import httpx  # noqa: E402
import pytest  # noqa: E402
from httpx import ASGITransport  # noqa: E402

from rentgraph.db import Base, SessionLocal, engine  # noqa: E402
from rentgraph.main import app  # noqa: E402
from rentgraph.models import Workspace  # noqa: E402
from rentgraph.services.runs import manager  # noqa: E402

SAMPLES = Path(__file__).parent / "samples"
TERMINAL = frozenset({"done", "failed", "cancelled", "interrupted"})


@pytest.fixture(scope="session", autouse=True)
def _tmp_env():
    yield
    shutil.rmtree(_TMP, ignore_errors=True)


@pytest.fixture(autouse=True)
async def _fresh_db():
    """每个用例：重建表结构 → 释放连接池（下个用例换事件循环时不会复用旧连接）。"""

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    for run_id in list(manager._runs):
        run = manager.get(run_id)
        if run is not None and not run.finished:
            await manager.cancel(run_id)
            if run.task is not None:
                with contextlib.suppress(Exception):
                    await run.task
    manager._runs.clear()
    await engine.dispose()


@pytest.fixture
async def client(_fresh_db):
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http


# ---------------- 常用操作 ----------------


async def create_workspace(client: httpx.AsyncClient) -> str:
    resp = await client.post("/api/v1/workspaces")
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


@pytest.fixture
async def workspace(client: httpx.AsyncClient) -> str:
    return await create_workspace(client)


async def wait_run(client: httpx.AsyncClient, run_id: str, timeout: float = 20.0) -> dict:
    """轮询运行直到终态；后台任务与请求共享事件循环，每次 GET 都让出控制权。"""

    deadline = asyncio.get_running_loop().time() + timeout
    last: dict = {}
    while asyncio.get_running_loop().time() < deadline:
        resp = await client.get(f"/api/v1/runs/{run_id}")
        if resp.status_code == 200:
            last = resp.json()
            if last["status"] in TERMINAL:
                return last
        await asyncio.sleep(0.01)
    raise AssertionError(f"run {run_id} 未在 {timeout}s 内结束：{last}")


async def collect_events(client: httpx.AsyncClient, run_id: str, timeout: float = 20.0) -> list[dict]:
    """读取 SSE 到终态，返回事件 data JSON 列表（含 run_id/seq/type 信封字段）。"""

    import json

    events: list[dict] = []

    async def read() -> None:
        async with client.stream("GET", f"/api/v1/runs/{run_id}/events") as resp:
            assert resp.status_code == 200
            async for line in resp.aiter_lines():
                if line.startswith("data:"):
                    events.append(json.loads(line.split(":", 1)[1].strip()))
                if events and events[-1].get("type") in {"done", "error", "cancelled"}:
                    return

    await asyncio.wait_for(read(), timeout=timeout)
    return events


async def add_house(client: httpx.AsyncClient, workspace_id: str, **fields) -> dict:
    payload = {"name": "测试房源", "source": "manual", **fields}
    resp = await client.post(f"/api/v1/houses?workspace_id={workspace_id}", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def import_batch(
    client: httpx.AsyncClient, workspace_id: str, text: str, source: str = "batch", **extra
) -> dict:
    resp = await client.post(
        "/api/v1/import-batches",
        json={"workspace_id": workspace_id, "source": source, "text": text, **extra},
    )
    assert resp.status_code == 202, resp.text
    batch = resp.json()
    await wait_run(client, batch["run_id"])
    got = await client.get(f"/api/v1/import-batches/{batch['id']}")
    assert got.status_code == 200, got.text
    return got.json()


async def upload_batch(client: httpx.AsyncClient, workspace_id: str, filename: str, data: bytes) -> dict:
    resp = await client.post(
        "/api/v1/import-batches/upload",
        data={"workspace_id": workspace_id},
        files={"file": (filename, data)},
    )
    assert resp.status_code == 202, resp.text
    batch = resp.json()
    await wait_run(client, batch["run_id"])
    got = await client.get(f"/api/v1/import-batches/{batch['id']}")
    assert got.status_code == 200, got.text
    return got.json()


async def confirm_batch(client: httpx.AsyncClient, batch: dict, houses: list[dict] | None = None):
    payload = houses if houses is not None else batch["drafts"]
    return await client.post(f"/api/v1/import-batches/{batch['id']}/confirm", json={"houses": payload})


async def upload_contract(
    client: httpx.AsyncClient, workspace_id: str, filename: str, data: bytes, **form
) -> dict:
    resp = await client.post(
        "/api/v1/contracts/upload",
        data={"workspace_id": workspace_id, **form},
        files={"file": (filename, data)},
    )
    assert resp.status_code == 202, resp.text
    payload = resp.json()
    run = await wait_run(client, payload["run_id"])
    return {"contract_id": payload["contract_id"], "run_id": payload["run_id"], "run": run}


async def create_contract(client: httpx.AsyncClient, workspace_id: str, text: str, **extra) -> dict:
    resp = await client.post("/api/v1/contracts", json={"workspace_id": workspace_id, "text": text, **extra})
    assert resp.status_code == 202, resp.text
    data = resp.json()
    run = await wait_run(client, data["run_id"])
    return {"contract_id": data["contract_id"], "run_id": data["run_id"], "run": run}


async def recommend(client: httpx.AsyncClient, workspace_id: str, view: str = "mix") -> dict:
    resp = await client.post("/api/v1/recommendations", json={"workspace_id": workspace_id, "view": view})
    assert resp.status_code == 202, resp.text
    data = resp.json()
    run = await wait_run(client, data["run_id"])
    got = await client.get(f"/api/v1/recommendations/{data['recommendation_id']}")
    assert got.status_code == 200, got.text
    return {"run": run, "run_id": data["run_id"], "recommendation": got.json()}


async def create_verification(
    client: httpx.AsyncClient, workspace_id: str, house_id: str, contract_id: str
) -> dict:
    resp = await client.post(
        "/api/v1/verifications",
        json={"workspace_id": workspace_id, "house_id": house_id, "contract_id": contract_id},
    )
    assert resp.status_code == 202, resp.text
    data = resp.json()
    run = await wait_run(client, data["run_id"])
    got = await client.get(f"/api/v1/verifications/{data['verification_id']}")
    assert got.status_code == 200, got.text
    return {"run": run, "verification": got.json()}


async def create_conversation(client: httpx.AsyncClient, workspace_id: str, title: str = "测试对话") -> str:
    resp = await client.post("/api/v1/conversations", json={"workspace_id": workspace_id, "title": title})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def ask(client: httpx.AsyncClient, conversation_id: str, text: str, **extra) -> dict:
    resp = await client.post(
        f"/api/v1/conversations/{conversation_id}/messages", json={"text": text, **extra}
    )
    assert resp.status_code == 202, resp.text
    data = resp.json()
    run = await wait_run(client, data["run_id"])
    return {"message_id": data["message_id"], "run_id": data["run_id"], "run": run}


async def expire_workspace(workspace_id: str) -> None:
    async with SessionLocal() as db:
        workspace = await db.get(Workspace, workspace_id)
        assert workspace is not None
        workspace.expires_at = datetime.now(UTC) - timedelta(hours=1)
        await db.commit()
