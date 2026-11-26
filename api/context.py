"""协程级会话上下文。

FastAPI 下多个请求跑在同一线程的不同 Task 里，全局变量会串台，threading.local 也失效，
因此会话目录与 thread_id 一律用 ContextVar：只要能拿到当前 Task，就能拿到自己的会话。
"""
from __future__ import annotations

from contextvars import ContextVar, Token
from typing import Optional

_session_dir: ContextVar[Optional[str]] = ContextVar("session_dir", default=None)
_thread_id: ContextVar[Optional[str]] = ContextVar("thread_id", default=None)
_task_started_at: ContextVar[Optional[float]] = ContextVar("task_started_at", default=None)


def set_session_context(session_dir: str) -> Token:
    return _session_dir.set(session_dir)


def get_session_context() -> Optional[str]:
    return _session_dir.get()


def set_thread_context(thread_id: str) -> Token:
    return _thread_id.set(thread_id)


def get_thread_context() -> Optional[str]:
    return _thread_id.get()


def set_task_start() -> None:
    import time

    _task_started_at.set(time.time())


def get_task_elapsed() -> float:
    import time

    started = _task_started_at.get()
    return 0.0 if started is None else round(time.time() - started, 2)


def reset_session_context(session_token: Token, thread_token: Token | None = None) -> None:
    """任务结束后恢复上下文，避免污染同线程的后续任务。"""
    try:
        _session_dir.reset(session_token)
    except ValueError:
        _session_dir.set(None)
    if thread_token is not None:
        try:
            _thread_id.reset(thread_token)
        except ValueError:
            _thread_id.set(None)
