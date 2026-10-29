"""WebSocket 连接管理与事件推送。

与"每个工具里手写 monitor.report_tool"的做法不同，本框架的事件主链路来自
agent.astream_events()，工具无需埋点。这里保留 emit() 供少量需要主动上报的位置
（如任务开始、异常、产物清单）使用。
"""
from __future__ import annotations

import asyncio
import datetime as _dt
import logging
from typing import Any

from fastapi import WebSocket

from api.context import get_thread_context

logger = logging.getLogger("deep_search.ws")


class ConnectionManager:
    """按 thread_id 分组管理 WebSocket，推送只发给对应会话。"""

    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = {}
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    @property
    def loop(self) -> asyncio.AbstractEventLoop | None:
        return self._loop

    async def connect(self, websocket: WebSocket, thread_id: str) -> None:
        await websocket.accept()
        self._connections.setdefault(thread_id, set()).add(websocket)
        logger.info("ws connected: thread=%s total=%d", thread_id, len(self._connections[thread_id]))

    def disconnect(self, websocket: WebSocket, thread_id: str) -> None:
        group = self._connections.get(thread_id)
        if not group:
            return
        group.discard(websocket)
        if not group:
            self._connections.pop(thread_id, None)

    def _snapshot(self, thread_id: str) -> list[WebSocket]:
        return list(self._connections.get(thread_id, ()))

    async def send_to_thread(self, thread_id: str, payload: dict[str, Any]) -> None:
        for ws in self._snapshot(thread_id):
            try:
                await ws.send_json(payload)
            except Exception:
                self.disconnect(ws, thread_id)

    def emit_from_thread(self, thread_id: str, payload: dict[str, Any]) -> None:
        """从非事件循环线程（或同步上下文）安全地投递消息。"""
        loop = self._loop
        if loop is None or not loop.is_running():
            logger.debug("monitor dropped (no loop): %s", payload.get("event"))
            return
        asyncio.run_coroutine_threadsafe(self.send_to_thread(thread_id, payload), loop)


manager = ConnectionManager()


def _payload(event: str, message: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "type": "monitor_event",
        "event": event,
        "message": message,
        "data": data or {},
        "timestamp": _dt.datetime.now().isoformat(timespec="seconds"),
    }


def emit(event: str, message: str, data: dict[str, Any] | None = None) -> None:
    """推送一条事件到当前 thread（thread_id 取自 ContextVar）。"""
    thread_id = get_thread_context()
    if not thread_id:
        logger.debug("[monitor:%s] %s", event, message)
        return
    manager.emit_from_thread(thread_id, _payload(event, message, data))


def report_session(thread_id: str, path: str) -> None:
    manager.emit_from_thread(
        thread_id, _payload("session_created", f"工作目录已就绪：{path}", {"path": path})
    )


def report_error(thread_id: str, message: str) -> None:
    manager.emit_from_thread(thread_id, _payload("error", f"执行失败：{message}"))


def report_result(thread_id: str, result: str, files: list[dict[str, Any]] | None = None) -> None:
    manager.emit_from_thread(
        thread_id,
        _payload("task_result", "任务执行完成", {"result": result, "files": files or []}),
    )
