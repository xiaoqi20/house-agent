"""运行创建与持久化的公共部分：把 RunContext 的状态落进 runs 表，供 GET /runs/{id} 查询。"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy import select

from ...db import SessionLocal
from ...models import Run, utcnow
from ..runs import RunContext, manager


async def persist_run(run: RunContext) -> None:
    async with SessionLocal() as db:
        row = await db.get(Run, run.id)
        if row is None:
            row = Run(id=run.id, kind=run.kind, workspace_id=run.workspace_id, thread_id=run.thread_id)
            db.add(row)
        row.status = run.status
        row.result = run.result
        row.error = run.error
        last = next((e for e in reversed(run.events) if e.type == "progress"), None)
        row.progress = dict(last.data) if last else dict(row.progress or {})
        if run.finished and row.finished_at is None:
            row.finished_at = utcnow()
        await db.commit()


async def create_run(
    kind: str,
    *,
    workspace_id: str | None = None,
    thread_id: str | None = None,
    house_id: str | None = None,
    contract_id: str | None = None,
) -> RunContext:
    run = manager.create(
        kind,
        workspace_id=workspace_id,
        thread_id=thread_id,
        house_id=house_id,
        contract_id=contract_id,
        persist=persist_run,
    )
    await persist_run(run)
    return run


def launch(run: RunContext, work: Callable[[RunContext], Awaitable[dict[str, Any] | None]]) -> RunContext:
    return manager.launch(run, work)


async def list_runs(workspace_id: str | None, limit: int = 20) -> list[Run]:
    async with SessionLocal() as db:
        stmt = select(Run).order_by(Run.created_at.desc()).limit(limit)
        if workspace_id:
            stmt = stmt.where(Run.workspace_id == workspace_id)
        return list((await db.execute(stmt)).scalars())


async def get_run_row(run_id: str) -> Run | None:
    async with SessionLocal() as db:
        return await db.get(Run, run_id)


async def cancel_run(run_id: str) -> RunContext | None:
    return await manager.cancel(run_id)


async def wait_task(run: RunContext) -> None:
    """测试用：等待后台任务结束。"""

    if run.task is not None:
        try:
            await asyncio.shield(run.task)
        except asyncio.CancelledError:
            pass
