"""L2 子智能体构建器。

每个构建器返回 deepagents 的 SubAgent 字典：name / description / prompt / tools / model。
description 直接决定主智能体的路由，务必写清适用与不适用边界。
"""
from __future__ import annotations

from typing import Any

from config.settings import settings
from prompt.loader import sub_prompt


def _model_override() -> dict[str, Any]:
    """子智能体可指定更便宜的模型；未配置则返回空字典沿用主模型。"""
    return {"model": settings.subagent_model} if settings.subagent_model else {}


def build_tavily_sub_agent() -> dict[str, Any]:
    from tools.internet_search import internet_search

    conf = sub_prompt("tavily")
    return {
        "name": conf["name"],
        "description": conf["description"],
        "prompt": conf["system_prompt"],
        "tools": [internet_search],
        **_model_override(),
    }


def build_db_sub_agent() -> dict[str, Any]:
    from tools.sql_tools import execute_sql_query, get_table_data, list_sql_tables

    conf = sub_prompt("db")
    return {
        "name": conf["name"],
        "description": conf["description"],
        "prompt": conf["system_prompt"],
        "tools": [list_sql_tables, get_table_data, execute_sql_query],
        **_model_override(),
    }


def build_rag_sub_agent() -> dict[str, Any]:
    from tools.ragflow_tools import ragflow_ask, ragflow_list_assistants

    conf = sub_prompt("ragflow")
    return {
        "name": conf["name"],
        "description": conf["description"],
        "prompt": conf["system_prompt"],
        "tools": [ragflow_list_assistants, ragflow_ask],
        **_model_override(),
    }
