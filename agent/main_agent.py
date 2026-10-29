"""Deep Search Agent 装配入口。

主智能体 = 文档生成工具 + 三个检索子智能体；检索工具不在主智能体工具集中，
从结构上杜绝"主智能体自己补数"。
"""
from __future__ import annotations

import os
from typing import Any, Iterable

from deepagents import create_deep_agent

from agent.sub_agents import build_db_sub_agent, build_rag_sub_agent, build_tavily_sub_agent
from agent.workspace import build_user_message, prepare_session
from config.settings import settings
from prompt.loader import main_prompt
from tools.file_tools import convert_md_to_pdf, generate_markdown, read_file_content

MAIN_TOOLS = [generate_markdown, convert_md_to_pdf, read_file_content]

_agent = None


def resolve_model() -> Any:
    """走 OpenAI 兼容网关时返回 ChatOpenAI 实例，否则返回 "provider:model" 字符串。"""
    if settings.model_base_url:
        from langchain_openai import ChatOpenAI

        model_name = settings.model.split(":", 1)[-1]
        api_key = settings.model_api_key or os.getenv("OPENAI_API_KEY", "not-needed")
        return ChatOpenAI(
            model=model_name,
            base_url=settings.model_base_url,
            api_key=api_key,
            temperature=0,
        )
    return settings.model


def build_agent(force_rebuild: bool = False):
    """构建（并缓存）主智能体。"""
    global _agent
    if _agent is not None and not force_rebuild:
        return _agent

    _agent = create_deep_agent(
        model=resolve_model(),
        tools=MAIN_TOOLS,
        system_prompt=main_prompt(),
        subagents=[
            build_tavily_sub_agent(),
            build_db_sub_agent(),
            build_rag_sub_agent(),
        ],
    )
    return _agent


def _iter_messages(result: dict[str, Any]) -> Iterable[Any]:
    return result.get("messages") or []


def extract_final_text(result: dict[str, Any]) -> str:
    """取最后一条有文本内容的 AI 消息。"""
    for message in reversed(list(_iter_messages(result))):
        content = getattr(message, "content", None)
        if isinstance(content, str) and content.strip():
            return content.strip()
        if isinstance(content, list):
            parts = [
                block.get("text", "")
                for block in content
                if isinstance(block, dict) and block.get("type") == "text"
            ]
            joined = "".join(parts).strip()
            if joined:
                return joined
    return ""


def run(question: str, session_id: str | None = None) -> dict[str, Any]:
    """同步执行一次深度检索任务。"""
    sid, workspace = prepare_session(session_id)
    agent = build_agent()
    result = agent.invoke({"messages": [{"role": "user", "content": build_user_message(question, workspace)}]})
    return {
        "session_id": sid,
        "workspace": str(workspace),
        "answer": extract_final_text(result),
        "messages": result.get("messages", []),
    }


async def arun(question: str, session_id: str | None = None) -> dict[str, Any]:
    """异步执行一次深度检索任务。"""
    sid, workspace = prepare_session(session_id)
    agent = build_agent()
    result = await agent.ainvoke(
        {"messages": [{"role": "user", "content": build_user_message(question, workspace)}]}
    )
    return {
        "session_id": sid,
        "workspace": str(workspace),
        "answer": extract_final_text(result),
        "messages": result.get("messages", []),
    }
