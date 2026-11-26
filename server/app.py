"""FastAPI + WebSocket 服务端。

把 deepagents/LangGraph 的事件流映射为前端可读的语义事件：
    run_start / delegation / tool_start / tool_end / token / run_end / error
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.main_agent import arun, build_agent  # noqa: E402
from agent.workspace import build_user_message, prepare_session  # noqa: E402

app = FastAPI(title="Deep Search Agent")


def _event_payload(event: dict[str, Any]) -> dict[str, Any] | None:
    """把 LangChain 事件转成前端协议。"""
    kind = event.get("event")
    name = event.get("name") or ""

    if kind == "on_tool_start":
        return {
            "type": "tool_start",
            "tool": name,
            "input": event.get("data", {}).get("input", {}),
        }
    if kind == "on_tool_end":
        output = event.get("data", {}).get("output")
        return {"type": "tool_end", "tool": name, "output": str(output)[:2000]}
    if kind == "on_chat_model_stream":
        chunk = event.get("data", {}).get("chunk")
        text = getattr(chunk, "content", "") if chunk is not None else ""
        if isinstance(text, str) and text:
            return {"type": "token", "text": text}
    return None


@app.websocket("/ws/{session_id}")
async def ws_endpoint(websocket: WebSocket, session_id: str) -> None:
    await websocket.accept()
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                payload = json.loads(raw)
                question = (payload.get("question") or "").strip()
            except json.JSONDecodeError:
                question = raw.strip()

            if not question:
                await websocket.send_json({"type": "error", "message": "问题为空"})
                continue

            sid, workspace = prepare_session(session_id)
            await websocket.send_json({"type": "run_start", "session_id": sid})

            try:
                agent = build_agent()
                final_state: dict[str, Any] = {}
                async for event in agent.astream_events(
                    {"messages": [{"role": "user", "content": build_user_message(question, workspace)}]},
                    version="v2",
                ):
                    if event.get("event") == "on_chain_end" and event.get("name") == "LangGraph":
                        final_state = event.get("data", {}).get("output") or {}
                    mapped = _event_payload(event)
                    if mapped:
                        await websocket.send_json(mapped)

                from agent.main_agent import extract_final_text

                await websocket.send_json(
                    {
                        "type": "run_end",
                        "session_id": sid,
                        "answer": extract_final_text(final_state),
                    }
                )
            except Exception as exc:  # 单轮异常不影响连接
                await websocket.send_json(
                    {"type": "error", "message": f"{type(exc).__name__}: {exc}"}
                )
    except WebSocketDisconnect:
        return


@app.post("/ask")
async def ask(question: str, session_id: str | None = None) -> dict[str, Any]:
    """HTTP 同步接口，便于脚本或后端联调。"""
    result = await arun(question, session_id)
    return {
        "session_id": result["session_id"],
        "answer": result["answer"],
        "workspace": result["workspace"],
    }
