"""FastAPI 服务端：任务提交、文件上传/下载/列表、WebSocket 进度推送。

事件协议（推送体统一 type=monitor_event）：
    tool_start / tool_end      工具执行
    assistant_call             委派子智能体（deepagents 内置 task 工具）
    token                      模型增量文本
    task_result                最终结果 + 产物清单
    session_created / error
"""
from __future__ import annotations

import asyncio
import logging
import shutil
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Query, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from agent.main_agent import build_agent, extract_final_text
from agent.workspace import build_user_message, prepare_session
from api.context import get_thread_context, set_session_context, set_task_start, set_thread_context
from api.monitor import manager, report_error, report_result, report_session
from tools.path_guard import resolve_in_workspace, use_workspace

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("deep_search.api")

app = FastAPI(title="Deep Search Agent", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_TASKS: dict[str, asyncio.Task] = {}


@app.on_event("startup")
async def _on_startup() -> None:
    # emit() 从同步上下文投递时需要事件循环引用，启动即绑定，避免首个任务早于 WS 连接而丢事件
    manager.bind_loop(asyncio.get_running_loop())


def _map_event(event: dict[str, Any]) -> dict[str, Any] | None:
    kind = event.get("event")
    name = event.get("name") or ""
    data = event.get("data") or {}

    if kind == "on_tool_start":
        tool_input = data.get("input") or {}
        if name == "task":
            sub = tool_input.get("subagent_type") or tool_input.get("name") or "子智能体"
            desc = tool_input.get("description") or tool_input.get("prompt") or ""
            return {
                "type": "monitor_event",
                "event": "assistant_call",
                "message": f"委派给「{sub}」",
                "data": {"assistant": sub, "task": str(desc)[:500]},
            }
        return {
            "type": "monitor_event",
            "event": "tool_start",
            "message": f"调用工具 {name}",
            "data": {"tool": name, "args": str(tool_input)[:500]},
        }

    if kind == "on_tool_end":
        output = data.get("output")
        return {
            "type": "monitor_event",
            "event": "tool_end",
            "message": f"工具 {name} 返回",
            "data": {"tool": name, "output": str(output)[:1500]},
        }

    if kind == "on_chat_model_stream":
        chunk = data.get("chunk")
        text = getattr(chunk, "content", "") if chunk is not None else ""
        if isinstance(text, str) and text:
            return {"type": "monitor_event", "event": "token", "message": "", "data": {"text": text}}

    return None


def _collect_outputs(workspace: Path) -> list[dict[str, Any]]:
    out_dir = workspace / "output"
    if not out_dir.exists():
        return []
    items = []
    for path in sorted(out_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if path.is_file():
            items.append(
                {"name": path.name, "size": path.stat().st_size, "path": path.relative_to(workspace).as_posix()}
            )
    return items


async def _run_task(thread_id: str, query: str) -> None:
    thread_token = set_thread_context(thread_id)
    set_task_start()

    # prepare_session 内部会建目录并绑定 ContextVar，返回后当前 Task 即拥有独立工作区
    _, workspace = prepare_session(thread_id)
    session_token = set_session_context(str(workspace))
    report_session(thread_id, str(workspace))

    try:
        agent = build_agent()
        final_state: dict[str, Any] = {}
        async for event in agent.astream_events(
            {"messages": [{"role": "user", "content": build_user_message(query, workspace)}]},
            version="v2",
        ):
            if event.get("event") == "on_chain_end" and event.get("name") == "LangGraph":
                final_state = event.get("data", {}).get("output") or {}
            payload = _map_event(event)
            if payload:
                await manager.send_to_thread(thread_id, payload)

        answer = extract_final_text(final_state)
        report_result(thread_id, answer, _collect_outputs(workspace))
    except Exception as exc:
        logger.exception("task failed: %s", thread_id)
        report_error(thread_id, f"{type(exc).__name__}: {exc}")
    finally:
        from api.context import reset_session_context

        reset_session_context(session_token, thread_token)


@app.post("/api/task")
async def create_task(query: str = Query(..., description="检索问题"),
                      thread_id: str | None = Query(None, description="会话 id，可选")) -> JSONResponse:
    tid = thread_id or uuid.uuid4().hex[:12]
    if tid in _TASKS and not _TASKS[tid].done():
        return JSONResponse({"status": "busy", "thread_id": tid}, status_code=409)

    task = asyncio.create_task(_run_task(tid, query))
    _TASKS[tid] = task
    task.add_done_callback(lambda _: _TASKS.pop(tid, None))
    return JSONResponse({"status": "started", "thread_id": tid})


@app.post("/api/upload")
async def upload_files(
    files: list[UploadFile] = File(...),
    thread_id: str = Query(..., description="会话 id"),
) -> JSONResponse:
    _, workspace = prepare_session(thread_id)
    upload_dir = workspace / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    saved: list[str] = []
    for item in files:
        safe_name = Path(item.filename or "upload.bin").name.replace("..", "_")
        target = (upload_dir / safe_name).resolve()
        # 二次确认：清洗后的路径仍必须在 uploads 目录内
        if upload_dir.resolve() not in target.parents:
            return JSONResponse({"status": "error", "message": f"非法文件名：{item.filename}"}, status_code=400)
        with target.open("wb") as fh:
            shutil.copyfileobj(item.file, fh)
        saved.append(safe_name)

    return JSONResponse({"status": "uploaded", "thread_id": thread_id, "files": saved})


@app.get("/api/files")
async def list_files(thread_id: str = Query(...), path: str = Query("output")) -> JSONResponse:
    _, workspace = prepare_session(thread_id)
    with use_workspace(workspace):
        try:
            base = resolve_in_workspace(path)
        except PermissionError as exc:
            return JSONResponse({"status": "error", "message": str(exc)}, status_code=400)

    if not base.exists():
        return JSONResponse({"status": "ok", "path": path, "files": []})

    files = []
    for item in sorted(base.rglob("*")):
        if item.is_file():
            stat = item.stat()
            files.append(
                {
                    "name": item.name,
                    "path": item.relative_to(workspace).as_posix(),
                    "size": stat.st_size,
                    "mtime": stat.st_mtime,
                }
            )
    files.sort(key=lambda x: x["mtime"], reverse=True)
    return JSONResponse({"status": "ok", "path": path, "files": files})


@app.get("/api/download")
async def download(thread_id: str = Query(...), path: str = Query(...)) -> Any:
    _, workspace = prepare_session(thread_id)
    with use_workspace(workspace):
        try:
            target = resolve_in_workspace(path, must_exist=True)
        except (PermissionError, FileNotFoundError) as exc:
            return JSONResponse({"status": "error", "message": str(exc)}, status_code=404)
    return FileResponse(target, filename=target.name)


@app.websocket("/ws/{thread_id}")
async def ws_endpoint(websocket: WebSocket, thread_id: str) -> None:
    manager.bind_loop(asyncio.get_running_loop())
    await manager.connect(websocket, thread_id)
    try:
        while True:
            message = await websocket.receive_text()
            if message == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        manager.disconnect(websocket, thread_id)
    except Exception:
        manager.disconnect(websocket, thread_id)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "thread": get_thread_context() or "none"}
