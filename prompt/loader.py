"""提示词加载与变量注入。

提示词与阈值配置分离：prompts.yml 里只写 ${变量}，加载时用 settings 注入，
避免改阈值还要动提示词文本。
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from config.settings import settings

_PLACEHOLDER = re.compile(r"\$\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


def _default_vars() -> dict[str, Any]:
    return {
        "max_searches": settings.max_searches_per_question,
        "sql_max_rows": settings.sql_max_rows,
        "preview_rows": settings.sql_table_preview_rows,
        "max_sql_fix_attempts": settings.max_sql_fix_attempts,
        "max_followups": 2,
        "workspace_hint": "由系统在用户消息中下发，不要自行拼接",
    }


def render(text: str, extra: dict[str, Any] | None = None) -> str:
    """把 ${key} 替换为实际值；未知占位符保留原样并在开发期可见。"""
    values = _default_vars()
    if extra:
        values.update(extra)

    def _sub(match: re.Match[str]) -> str:
        key = match.group(1)
        return str(values[key]) if key in values else match.group(0)

    return _PLACEHOLDER.sub(_sub, text)


def _render_tree(node: Any, extra: dict[str, Any] | None = None) -> Any:
    if isinstance(node, str):
        return render(node, extra)
    if isinstance(node, dict):
        return {k: _render_tree(v, extra) for k, v in node.items()}
    if isinstance(node, list):
        return [_render_tree(item, extra) for item in node]
    return node


@lru_cache(maxsize=4)
def load_prompts(path: str | None = None) -> dict[str, Any]:
    """加载并渲染提示词树，带缓存（同一进程内只读一次）。"""
    prompts_file = Path(path) if path else settings.prompts_file
    raw = yaml.safe_load(prompts_file.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"提示词文件格式错误：{prompts_file}")
    return _render_tree(raw)


def main_prompt() -> str:
    return load_prompts()["main_agent"]["system_prompt"]


def sub_prompt(key: str) -> dict[str, str]:
    """返回子智能体配置片段：name / description / system_prompt。"""
    node = load_prompts()["sub_agents"][key]
    return {
        "name": node["name"],
        "description": node["description"],
        "system_prompt": node["system_prompt"],
    }
