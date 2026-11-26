"""只读 SQL 工具（list / preview / query）。

安全边界在执行层而非提示词：
1. 必须以 SELECT 或 WITH 开头；
2. 命中任何写关键字直接拒绝；
3. 禁止多语句（分号结尾除外）；
4. 明细查询强制补 LIMIT，聚合查询可豁免。
"""
from __future__ import annotations

import re
from functools import lru_cache
from typing import Any

from langchain_core.tools import tool
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from config.settings import settings

_WRITE_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE|REPLACE|GRANT|REVOKE|"
    r"CALL|EXEC|EXECUTE|RENAME|LOCK|UNLOCK|MERGE|SET|USE|LOAD\s+DATA|INTO\s+OUTFILE)\b",
    re.IGNORECASE,
)
_LEADING_OK = re.compile(r"^\s*(SELECT|WITH)\b", re.IGNORECASE)
_HAS_LIMIT = re.compile(r"\blimit\s+\d+", re.IGNORECASE)
_HAS_AGG = re.compile(
    r"\b(count|sum|avg|min|max|group\s+by|distinct)\b", re.IGNORECASE
)
_SENSITIVE_FIELDS = re.compile(
    r"(phone|mobile|tel|id_card|idcard|identity|email|address|password)", re.IGNORECASE
)


class ReadOnlyViolation(ValueError):
    """SQL 不是合法只读查询。"""


def assert_read_only(sql: str) -> str:
    """校验并返回清洗后的单条 SQL；不合规直接抛 ReadOnlyViolation。"""
    statement = (sql or "").strip().rstrip(";").strip()
    if not statement:
        raise ReadOnlyViolation("SQL 为空。")

    if not _LEADING_OK.match(statement):
        raise ReadOnlyViolation("只允许 SELECT / WITH 开头的只读查询。")

    if _WRITE_KEYWORDS.search(statement):
        raise ReadOnlyViolation("检测到写操作或结构变更关键字，已拒绝执行。")

    if ";" in statement:
        raise ReadOnlyViolation("禁止一次提交多条语句。")

    if "--" in statement or "/*" in statement:
        raise ReadOnlyViolation("禁止在 SQL 中使用注释，避免绕过校验。")

    return statement


def _apply_row_limit(statement: str, max_rows: int) -> str:
    if _HAS_LIMIT.search(statement):
        # 已有 LIMIT：把超过上限的行数压回上限
        def _clamp(match: re.Match[str]) -> str:
            value = int(match.group(1))
            return f"LIMIT {min(value, max_rows)}"

        return re.sub(r"\blimit\s+(\d+)", _clamp, statement, flags=re.IGNORECASE)
    if _HAS_AGG.search(statement):
        return statement
    return f"{statement} LIMIT {max_rows}"


@lru_cache(maxsize=1)
def _engine() -> Engine:
    if not settings.db_url:
        raise RuntimeError("未配置 DS_AGENT_DB_URL。")
    url = settings.db_url
    connect_args: dict[str, Any] = {}
    if url.startswith("mysql"):
        # pymysql 默认按 latin1 解码，中文会变乱码；显式声明 utf8mb4 并同步进连接串
        connect_args["charset"] = "utf8mb4"
        if "charset=" not in url:
            url = f"{url}{'&' if '?' in url else '?'}charset=utf8mb4"
    return create_engine(url, pool_pre_ping=True, future=True, connect_args=connect_args)


def _to_markdown(rows: list[dict[str, Any]], max_cols: int = 20) -> str:
    if not rows:
        return "（无记录）"
    columns = list(rows[0].keys())[:max_cols]
    header = "| " + " | ".join(columns) + " |"
    divider = "| " + " | ".join("---" for _ in columns) + " |"
    body: list[str] = []
    for row in rows:
        cells = []
        for col in columns:
            value = row.get(col)
            if _SENSITIVE_FIELDS.search(col) and value not in (None, ""):
                cells.append("***已脱敏***")
            else:
                cells.append("" if value is None else str(value))
        body.append("| " + " | ".join(cells) + " |")
    return "\n".join([header, divider, *body])


@tool
def list_sql_tables() -> str:
    """列出当前数据库的全部表名，作为查询流程的第一步。"""
    try:
        tables = sorted(inspect(_engine()).get_table_names())
    except (RuntimeError, SQLAlchemyError) as exc:
        return f"表清单获取失败：{exc}"
    if not tables:
        return "数据库中没有任何表。"
    return "可用表清单：\n" + "\n".join(f"- {name}" for name in tables)


@tool
def get_table_data(table_name: str) -> str:
    """读取指定表的前若干行，用于确认字段名、字段含义与数据形态。

    Args:
        table_name: 表名，必须是 list_sql_tables 返回过的表。
    """
    try:
        engine = _engine()
        tables = inspect(engine).get_table_names()
    except (RuntimeError, SQLAlchemyError) as exc:
        return f"表结构获取失败：{exc}"

    if table_name not in tables:
        return f"表 {table_name} 不存在，请先调用 list_sql_tables 确认表名。"

    columns = inspect(engine).get_columns(table_name)
    col_desc = "\n".join(
        f"- {col['name']} ({col['type']})" for col in columns
    )
    limit = settings.sql_table_preview_rows

    try:
        with engine.connect() as conn:
            result = conn.execute(text(f"SELECT * FROM `{table_name}` LIMIT {limit}"))
            rows = [dict(row._mapping) for row in result]
    except SQLAlchemyError as exc:
        return f"表数据读取失败：{exc}"

    return (
        f"表：{table_name}\n字段结构：\n{col_desc}\n\n"
        f"前 {limit} 行样例：\n{_to_markdown(rows)}"
    )


@tool
def execute_sql_query(sql: str, purpose: str = "") -> str:
    """执行只读 SQL 取数（仅 SELECT / WITH，自动限行、自动脱敏）。

    Args:
        sql: 单条 SELECT 查询语句。
        purpose: 本次查询的业务目的，用于结果溯源。
    """
    try:
        statement = assert_read_only(sql)
    except ReadOnlyViolation as exc:
        return f"SQL 被拒绝：{exc}"

    statement = _apply_row_limit(statement, settings.sql_max_rows)

    try:
        with _engine().connect() as conn:
            result = conn.execute(text(statement))
            rows = [dict(row._mapping) for row in result]
    except SQLAlchemyError as exc:
        return (
            f"查询执行失败：{exc}\n"
            f"已执行 SQL：{statement}\n"
            "请先回到 list_sql_tables / get_table_data 核对表名与字段名，不要重复试错同一语句。"
        )

    head = f"查询目的：{purpose or '未注明'}\n实际执行 SQL：{statement}\n返回行数：{len(rows)}\n\n"
    return head + _to_markdown(rows)
