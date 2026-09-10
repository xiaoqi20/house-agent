"""运行管理与 SSE 事件流（对应选型文档 §8：先创建任务，再订阅事件）。

一期实现为进程内 RunManager：每个 run 一个 asyncio 任务 + 事件日志 + 取消标记 + 订阅队列。
接口形状（run_id/thread_id/workspace_id + 统一事件信封 + Last-Event-ID 重连）与文档一致，
生产替换成 Redis Stream + ARQ Worker 时不需要改前端协议。

隔离承诺（PRD §9.2）：
- 事件只属于创建它的 run，调用方只消费当前 run_id；
- 取消在节点边界生效（工作流调用 `run.check_cancelled()`）；
- 完成后事件保留在 run 的日志里，重连可回放，但不会写入别的会话/房源。
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from ..errors import AppError, error_body
from ..models import uid

logger = logging.getLogger("rentgraph.runs")

TERMINAL_EVENTS = frozenset({"done", "error", "cancelled"})
MAX_EVENTS = 5000


class RunCancelled(Exception):
    """工作流在节点边界检测到取消标记时抛出。"""


@dataclass
class RunEvent:
    type: str
    data: dict[str, Any]
    seq: int
    run_id: str
    workspace_id: str | None = None
    thread_id: str | None = None
    house_id: str | None = None
    contract_id: str | None = None
    ts: float = field(default_factory=time.time)

    @property
    def event_id(self) -> str:
        return str(self.seq)

    def payload(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "type": self.type,
            "run_id": self.run_id,
            "workspace_id": self.workspace_id,
            "thread_id": self.thread_id,
            "house_id": self.house_id,
            "contract_id": self.contract_id,
            "seq": self.seq,
            "data": self.data,
        }


@dataclass
class RunContext:
    """单个运行：事件日志 + 订阅者 + 取消标记 + 终态。"""

    id: str
    kind: str
    workspace_id: str | None = None
    thread_id: str | None = None
    house_id: str | None = None
    contract_id: str | None = None
    status: str = "queued"
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    task: asyncio.Task | None = None
    seq: int = 0
    events: list[RunEvent] = field(default_factory=list)
    subscribers: set[asyncio.Queue] = field(default_factory=set)
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    persist: Callable[[RunContext], Awaitable[None]] | None = None

    # ---------- 状态 ----------
    @property
    def finished(self) -> bool:
        return self.status in {"done", "failed", "cancelled", "interrupted"}

    @property
    def cancelled(self) -> bool:
        return self.cancel_event.is_set()

    def check_cancelled(self) -> None:
        if self.cancelled:
            raise RunCancelled()

    async def sleep(self, seconds: float) -> None:
        """可被取消的等待（步骤之间的让出点）。"""

        try:
            await asyncio.wait_for(self.cancel_event.wait(), timeout=seconds)
        except TimeoutError:
            return
        raise RunCancelled()

    # ---------- 事件 ----------
    async def emit(
        self,
        type: str,
        data: dict[str, Any] | None = None,
        *,
        house_id: str | None = None,
        contract_id: str | None = None,
    ) -> RunEvent:
        self.seq += 1
        event = RunEvent(
            type=type,
            data=data or {},
            seq=self.seq,
            run_id=self.id,
            workspace_id=self.workspace_id,
            thread_id=self.thread_id,
            house_id=house_id if house_id is not None else self.house_id,
            contract_id=contract_id if contract_id is not None else self.contract_id,
        )
        self.events.append(event)
        if len(self.events) > MAX_EVENTS:
            del self.events[: len(self.events) - MAX_EVENTS]
        for queue in list(self.subscribers):
            queue.put_nowait(event)
        return event

    async def progress(
        self, step: str, index: int, label: str, status: str = "active", detail: str = ""
    ) -> RunEvent:
        return await self.emit(
            "progress",
            {"step": step, "index": index, "label": label, "status": status, "detail": detail},
        )

    async def token(self, text: str) -> RunEvent:
        return await self.emit("token", {"text": text})

    def subscribe(self, last_event_id: int | None = None) -> AsyncIterator[RunEvent]:
        """回放 + 订阅：先注册队列再回放，避免回放与实时之间的丢失。"""

        async def generator() -> AsyncIterator[RunEvent]:
            queue: asyncio.Queue = asyncio.Queue()
            self.subscribers.add(queue)
            last_seq = last_event_id or 0
            try:
                for event in list(self.events):
                    if event.seq > last_seq:
                        yield event
                        last_seq = event.seq
                if self.finished:
                    return
                while True:
                    event = await queue.get()
                    if event.seq <= last_seq:
                        continue
                    yield event
                    last_seq = event.seq
                    if event.type in TERMINAL_EVENTS:
                        return
            finally:
                self.subscribers.discard(queue)

        return generator()

    # ---------- 终态 ----------
    async def finish_done(self, result: dict[str, Any] | None = None) -> None:
        self.status = "done"
        self.result = result
        await self.emit("done", {"result": result or {}})
        await self._persist()

    async def finish_error(self, exc: BaseException) -> None:
        body = error_body(exc)
        self.status = "failed"
        self.error = body
        await self.emit("error", body)
        await self._persist()

    async def finish_cancelled(self, reason: str = "user") -> None:
        self.status = "cancelled"
        await self.emit("cancelled", {"reason": reason})
        await self._persist()

    async def interrupt(self, data: dict[str, Any]) -> None:
        """等待用户确认（如字段确认）时的挂起点，不算终态。"""

        self.status = "interrupted"
        await self.emit("interrupt", data)
        await self._persist()

    async def _persist(self) -> None:
        if self.persist is not None:
            try:
                await self.persist(self)
            except Exception:  # 持久化失败不得影响事件流
                pass


class RunManager:
    """进程内运行表。`launch` 统一处理 done/error/cancelled 三种终态。"""

    def __init__(self) -> None:
        self._runs: dict[str, RunContext] = {}

    def create(
        self,
        kind: str,
        *,
        workspace_id: str | None = None,
        thread_id: str | None = None,
        house_id: str | None = None,
        contract_id: str | None = None,
        persist: Callable[[RunContext], Awaitable[None]] | None = None,
    ) -> RunContext:
        run = RunContext(
            id=uid(),
            kind=kind,
            workspace_id=workspace_id,
            thread_id=thread_id,
            house_id=house_id,
            contract_id=contract_id,
            persist=persist,
        )
        self._runs[run.id] = run
        return run

    def get(self, run_id: str) -> RunContext | None:
        return self._runs.get(run_id)

    def register(self, run: RunContext) -> RunContext:
        self._runs[run.id] = run
        return run

    def launch(
        self,
        run: RunContext,
        work: Callable[[RunContext], Awaitable[dict[str, Any] | None]],
    ) -> RunContext:
        """启动工作流：终态处理集中在这里，工作流只负责业务和 `check_cancelled()`。"""

        async def runner() -> None:
            run.status = "running"
            await run.emit("progress", {"step": "start", "index": 0, "label": "已开始", "status": "active"})
            try:
                result = await work(run)
                if run.cancelled:
                    await run.finish_cancelled()
                else:
                    await run.finish_done(result)
            except RunCancelled:
                await run.finish_cancelled()
            except asyncio.CancelledError:
                await run.finish_cancelled(reason="cancelled")
                raise
            except AppError as exc:
                logger.warning("run_failed kind=%s run=%s code=%s message=%s", run.kind, run.id, exc.code, exc.message)
                await run.finish_error(exc)
            except Exception as exc:  # noqa: BLE001 - 统一转错误事件
                logger.exception("run_failed kind=%s run=%s", run.kind, run.id)
                await run.finish_error(exc)

        run.task = asyncio.create_task(runner(), name=f"run-{run.kind}-{run.id}")
        return run

    async def cancel(self, run_id: str, reason: str = "user") -> RunContext | None:
        run = self.get(run_id)
        if run is None:
            return None
        if run.finished:
            return run
        run.cancel_event.set()
        if run.task is not None:
            run.task.cancel()
        # 让 runner 的 CancelledError 分支发出 cancelled 事件
        await asyncio.sleep(0)
        if run.status not in {"cancelled", "done", "failed"}:
            await run.finish_cancelled(reason)
        return run

    def drop(self, run_id: str) -> None:
        self._runs.pop(run_id, None)


manager = RunManager()
