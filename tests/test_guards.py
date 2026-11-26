"""执行层防护的单元测试：只读 SQL 校验 + 工作目录沙箱。"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.path_guard import (  # noqa: E402
    WorkspaceViolation,
    create_session_workspace,
    resolve_in_workspace,
)
from tools.sql_tools import ReadOnlyViolation, _apply_row_limit, assert_read_only  # noqa: E402


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM orders",
        "select id, sum(amount) from orders group by id",
        "WITH t AS (SELECT 1) SELECT * FROM t",
    ],
)
def test_read_only_accepts_select(sql: str) -> None:
    assert assert_read_only(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM orders",
        "SELECT 1; DROP TABLE orders",
        "UPDATE orders SET amount = 0",
        "SELECT * INTO OUTFILE '/tmp/x' FROM orders",
        "SELECT * FROM orders -- comment",
        "",
    ],
)
def test_read_only_rejects_dangerous(sql: str) -> None:
    with pytest.raises(ReadOnlyViolation):
        assert_read_only(sql)


def test_row_limit_applied() -> None:
    assert _apply_row_limit("SELECT * FROM t", 200).endswith("LIMIT 200")
    assert _apply_row_limit("SELECT * FROM t LIMIT 9999", 200).endswith("LIMIT 200")
    # 聚合语句不追加 LIMIT
    assert "LIMIT" not in _apply_row_limit("SELECT count(*) FROM t", 200)


def test_workspace_blocks_traversal() -> None:
    create_session_workspace("pytest_guard")
    inside = resolve_in_workspace("output/report.md")
    assert inside.name == "report.md"

    with pytest.raises(WorkspaceViolation):
        resolve_in_workspace("../../etc/passwd")

    # 越界样本必须在任何平台上都真的在目录外：写死 "C:/Windows/..." 时
    # Linux 会把它当普通相对名落回 workspace 内，守卫等于没被验证过。
    for outside in (Path(sys.executable), Path(tempfile.gettempdir()) / "ds_guard_probe"):
        with pytest.raises(WorkspaceViolation):
            resolve_in_workspace(str(outside))
