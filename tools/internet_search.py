"""网络检索工具（Tavily）。

提示词里写了"单问题上限 3 次"，这里用预算计数器把它变成硬约束：
超预算的调用直接返回拒绝信息，模型无法通过换词绕过。
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator, Literal

from langchain_core.tools import tool

from config.settings import settings

_search_counter: ContextVar[dict[str, int]] = ContextVar("ds_search_counter", default=None)


@contextmanager
def search_budget(limit: int | None = None) -> Iterator[dict[str, int]]:
    """为一次子任务开启检索预算上下文。"""
    budget = {"used": 0, "limit": limit or settings.max_searches_per_question}
    token = _search_counter.set(budget)
    try:
        yield budget
    finally:
        _search_counter.reset(token)


def _consume() -> tuple[bool, int, int]:
    budget = _search_counter.get()
    if budget is None:
        # 未开预算上下文时退化为单次放行，避免工具不可用
        return True, 0, settings.max_searches_per_question
    if budget["used"] >= budget["limit"]:
        return False, budget["used"], budget["limit"]
    budget["used"] += 1
    return True, budget["used"], budget["limit"]


def _format_results(payload: dict) -> str:
    results = payload.get("results") or []
    if not results:
        return "未检索到可靠来源。"
    lines: list[str] = []
    for idx, item in enumerate(results, start=1):
        title = item.get("title") or "无标题"
        url = item.get("url") or ""
        published = item.get("published_date") or item.get("published") or "时间未知"
        content = (item.get("content") or "").strip().replace("\n", " ")
        lines.append(f"{idx}. {title}\n   来源：{url}\n   时间：{published}\n   摘要：{content[:500]}")
    return "\n".join(lines)


@tool
def internet_search(
    query: str,
    topic: Literal["general", "news", "finance"] = "general",
    max_results: int = 5,
    days: int = 0,
) -> str:
    """检索公开互联网信息。

    Args:
        query: 具体检索问题，需包含主体、时间范围、地域或指标口径。
        topic: 检索分类，general 通用 / news 新闻时事 / finance 财经。
        max_results: 返回结果条数，默认 5。
        days: 仅返回最近 N 天的结果，0 表示不限。
    """
    if not settings.tavily_api_key:
        return "检索不可用：未配置 TAVILY_API_KEY。"

    allowed, used, limit = _consume()
    if not allowed:
        return (
            f"检索预算已用尽（{used}/{limit}）。请立即基于已有结果作答，"
            "不要继续更换关键词重搜；如需更多信息，请在上游说明数据缺口。"
        )

    try:
        from tavily import TavilyClient
    except ModuleNotFoundError:
        return "检索不可用：缺少 tavily-python 依赖。"

    client = TavilyClient(api_key=settings.tavily_api_key)
    kwargs: dict = {
        "query": query,
        "topic": topic,
        "max_results": max(1, min(int(max_results), 10)),
        "include_answer": False,
    }
    if days and days > 0:
        kwargs["days"] = int(days)

    try:
        payload = client.search(**kwargs)
    except Exception as exc:  # 网络或配额异常，如实回传，不重试
        return f"检索失败：{type(exc).__name__}: {exc}"

    header = f"[检索 {used}/{limit}] query={query} topic={topic}\n"
    return header + _format_results(payload)
