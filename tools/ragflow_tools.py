"""RAGFlow 知识库工具：助手列表 + 助手问答。

不同版本 RAGFlow 的接口路径有差异，这里集中在 _api_base 与两个端点函数里，
换版本只需改端点常量，不必改提示词与子智能体代码。
"""
from __future__ import annotations

from typing import Any

import requests
from langchain_core.tools import tool

from config.settings import settings

_LIST_ENDPOINT = "/api/v1/chats"
_ASK_ENDPOINT = "/api/v1/chats/{chat_id}/completions"


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.ragflow_api_key}",
        "Content-Type": "application/json",
    }


def _base() -> str:
    if not settings.ragflow_base_url or not settings.ragflow_api_key:
        raise RuntimeError("未配置 RAGFLOW_BASE_URL / RAGFLOW_API_KEY。")
    return settings.ragflow_base_url.rstrip("/")


def _truncate(text: str, limit: int = 2000) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[:limit] + "……（已截断）"


@tool
def ragflow_list_assistants() -> str:
    """列出可用的 RAGFlow 知识库助手，用于决定问题应该落到哪个知识库。"""
    try:
        resp = requests.get(
            _base() + _LIST_ENDPOINT,
            headers=_headers(),
            params={"page": 1, "page_size": 100},
            timeout=settings.request_timeout,
        )
        resp.raise_for_status()
        payload: dict[str, Any] = resp.json()
    except Exception as exc:
        return f"知识库助手列表获取失败：{type(exc).__name__}: {exc}"

    data = payload.get("data") or []
    if not data:
        return "知识库中没有可用的助手，或当前 API Key 无访问权限。"

    lines = []
    for item in data:
        name = item.get("name") or "未命名"
        chat_id = item.get("id") or ""
        desc = (item.get("description") or "").strip().replace("\n", " ")
        lines.append(f"- {name} | id={chat_id}\n  说明：{desc[:200] or '无'}")
    return "可用知识库助手：\n" + "\n".join(lines)


@tool
def ragflow_ask(chat_id: str, question: str) -> str:
    """向指定知识库助手提问，返回结论与原文依据。

    Args:
        chat_id: 知识库助手 id，来自 ragflow_list_assistants。
        question: 具体问题，建议包含对象、时间、指标或条款编号。
    """
    if not chat_id or not question.strip():
        return "参数缺失：chat_id 与 question 均为必填。"

    try:
        resp = requests.post(
            _base() + _ASK_ENDPOINT.format(chat_id=chat_id),
            headers=_headers(),
            json={"question": question, "stream": False},
            timeout=settings.request_timeout,
        )
        resp.raise_for_status()
        payload: dict[str, Any] = resp.json()
    except Exception as exc:
        return f"知识库问答失败：{type(exc).__name__}: {exc}"

    data = payload.get("data") or {}
    answer = data.get("answer") or ""
    references = data.get("reference") or {}

    if not answer:
        return "知识库中未收录该信息（助手未返回有效答案）。"

    chunks: list[str] = []
    if isinstance(references, dict):
        for _, items in references.items():
            for chunk in items or []:
                content = _truncate(chunk.get("content") or "", 400)
                doc = chunk.get("document_name") or chunk.get("doc_name") or "未知文档"
                if content:
                    chunks.append(f"[{doc}] {content}")

    head = f"结论：\n{_truncate(answer, 3000)}"
    if chunks:
        head += "\n\n原文依据：\n" + "\n".join(f"- {c}" for c in chunks[:8])
    return head
