"""统一运行接口：查询状态、订阅 SSE 事件、取消（选型文档 §8）。"""

from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends, Header
from fastapi.sse import EventSourceResponse, ServerSentEvent
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..errors import AppError
from ..models import Run
from ..schemas.common import RunOut
from ..services.runs import RunContext, manager
from .deps import http_error

router = APIRouter(prefix="/runs", tags=["runs"])

_FINAL_EVENT = {"done": "done", "failed": "error", "cancelled": "cancelled", "interrupted": "interrupt"}


def _progress_of(run) -> dict:
    """RunContext 上的 progress 是方法，这里取最近一次 progress 事件的数据。"""

    last = next((event for event in reversed(run.events) if event.type == "progress"), None)
    return dict(last.data) if last is not None else {}


def _run_out(run) -> RunOut:
    return RunOut(
        id=run.id,
        kind=run.kind,
        status=run.status,
        workspace_id=run.workspace_id,
        thread_id=run.thread_id,
        progress=_progress_of(run),
        result=run.result if isinstance(run.result, dict) else None,
        error=run.error,
    )


@router.get("/{run_id}", response_model=RunOut)
async def get_run(run_id: str, db: Annotated[AsyncSession, Depends(get_db)]) -> RunOut:
    run = manager.get(run_id)
    if run is not None:
        return _run_out(run)
    row = await db.get(Run, run_id)
    if row is None:
        raise http_error(AppError("NOT_FOUND", "运行不存在或已被清理（重新发起即可）"))
    return RunOut(
        id=row.id,
        kind=row.kind,
        status=row.status,
        workspace_id=row.workspace_id,
        thread_id=row.thread_id,
        progress=dict(row.progress or {}),
        result=row.result,
        error=row.error,
    )


async def _event_target(
    run_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> tuple[RunContext | None, Run | None]:
    """订阅目标：内存中的运行优先，否则读库；都没有则 404。

    必须是依赖而不是生成器函数体里的判断：SSE 一开始推流状态码就发出去了，
    生成器里再 raise 404 客户端只会收到一个 200 的空流。
    """

    live = manager.get(run_id)
    if live is not None:
        return live, None
    row = await db.get(Run, run_id)
    if row is None:
        raise http_error(AppError("NOT_FOUND", "运行不存在或已被清理"))
    return None, row


@router.get("/{run_id}/events", response_class=EventSourceResponse)
async def run_events(
    target: Annotated[tuple[RunContext | None, Run | None], Depends(_event_target)],
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
):
    """SSE：支持 Last-Event-ID 重连；运行已结束后回放并收尾。

    用 FastAPI 内置 SSE 编码（`fastapi.sse`）：自动补 `Cache-Control: no-cache`、
    `X-Accel-Buffering: no` 与 15s 心跳注释（等价于原先 sse-starlette 的 ping=15）。
    """

    live, row = target
    if live is not None:
        try:
            last_seq = int(last_event_id) if last_event_id else None
        except ValueError:
            last_seq = None
        async for event in live.subscribe(last_seq):
            yield ServerSentEvent(
                raw_data=json.dumps(event.payload(), ensure_ascii=False),
                event=event.type,
                id=event.event_id,
            )
        return

    assert row is not None  # 依赖已保证二选一
    payload = {
        "event_id": "1",
        "type": _FINAL_EVENT.get(row.status, "error"),
        "run_id": row.id,
        "workspace_id": row.workspace_id,
        "thread_id": row.thread_id,
        "house_id": None,
        "contract_id": None,
        "seq": 1,
        "data": (
            {"result": row.result}
            if row.status == "done"
            else {"code": "RUN_FINISHED", "message": row.status}
        ),
    }
    yield ServerSentEvent(
        raw_data=json.dumps(payload, ensure_ascii=False, default=str), event=payload["type"], id="1"
    )


@router.post("/{run_id}/cancel", response_model=RunOut)
async def cancel_run(run_id: str, db: Annotated[AsyncSession, Depends(get_db)]) -> RunOut:
    run = await manager.cancel(run_id)
    if run is None:
        row = await db.get(Run, run_id)
        if row is None:
            raise http_error(AppError("NOT_FOUND", "运行不存在或已结束"))
        return RunOut(
            id=row.id,
            kind=row.kind,
            status=row.status,
            workspace_id=row.workspace_id,
            thread_id=row.thread_id,
            progress=dict(row.progress or {}),
            result=row.result,
            error=row.error,
        )
    return _run_out(run)
