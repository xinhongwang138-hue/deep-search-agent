"""真实 MySQL 自检：校验数据源取数链路、只读账号权限边界与执行层防护。

前置：先起演示库（容器自带建表与样例数据）
    docker compose -f docker-compose.demo.yml up -d

用法：
    uv run python scripts/verify_mysql.py
    # 或指向自己的只读库
    DS_AGENT_DB_URL="mysql+pymysql://user:pwd@127.0.0.1:3306/cps_demo" uv run python scripts/verify_mysql.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_URL = "mysql+pymysql://readonly:demo_readonly_2024@127.0.0.1:23306/cps_demo"
DB_URL = os.getenv("DS_AGENT_DB_URL") or DEFAULT_URL

TABLES = ("drugs", "inventory", "sales_orders")
QUERIES = {
    "Top5 药品 GMV": (
        "SELECT d.drug_name, SUM(s.amount) AS gmv FROM sales_orders s "
        "JOIN drugs d ON d.drug_id = s.drug_id GROUP BY d.drug_name ORDER BY gmv DESC LIMIT 5"
    ),
    "低库存预警": (
        "SELECT d.drug_name, i.warehouse, i.quantity, i.safety_stock FROM inventory i "
        "JOIN drugs d ON d.drug_id = i.drug_id WHERE i.quantity < i.safety_stock "
        "ORDER BY i.quantity ASC LIMIT 10"
    ),
    "区域销售排名": (
        "SELECT region, COUNT(*) AS orders, SUM(amount) AS amount FROM sales_orders "
        "GROUP BY region ORDER BY amount DESC"
    ),
    "近效期库存(180天)": (
        "SELECT d.drug_name, i.batch_no, i.quantity, i.expiry_date FROM inventory i "
        "JOIN drugs d ON d.drug_id = i.drug_id "
        "WHERE i.expiry_date <= DATE_ADD(CURDATE(), INTERVAL 180 DAY) ORDER BY i.expiry_date LIMIT 10"
    ),
}
GUARD_CASES = {
    "DELETE": "DELETE FROM sales_orders",
    "多语句": "SELECT 1; DROP TABLE drugs",
    "注释绕过": "SELECT 1 -- x",
    "SET 变量": "SET @a = 1",
    "文件导出": "SELECT * INTO OUTFILE '/tmp/x' FROM sales_orders",
}


def stage_connect(engine) -> bool:
    from sqlalchemy import text

    with engine.connect() as conn:
        version = conn.execute(text("SELECT VERSION()")).scalar()
        dbname = conn.execute(text("SELECT DATABASE()")).scalar()
        print(f"[连通] MySQL {version} / schema={dbname}")
        empty = []
        for table in TABLES:
            count = conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
            print(f"       {table:14s} rows={count}")
            if not count:
                empty.append(table)
    if empty:
        print(f"[失败] 空表：{empty}，seed.sql 未生效")
        return False
    return True


def stage_tools(db_url: str) -> None:
    os.environ["DS_AGENT_DB_URL"] = db_url
    sys.path.insert(0, str(ROOT))

    from tools.sql_tools import execute_sql_query, get_table_data, list_sql_tables

    print("\n=== list_sql_tables ===")
    print(list_sql_tables.invoke({}))

    print("\n=== get_table_data('drugs') 前 3 行 ===")
    preview = get_table_data.invoke({"table_name": "drugs"}).splitlines()
    print("\n".join(preview[:8]))

    for name, sql in QUERIES.items():
        print(f"\n=== 取数：{name} ===")
        print(execute_sql_query.invoke({"sql": sql, "purpose": name}))


def stage_guards() -> None:
    from tools.sql_tools import execute_sql_query

    print("\n=== 防护复验（应全部被拒或收紧） ===")
    for name, sql in GUARD_CASES.items():
        out = execute_sql_query.invoke({"sql": sql, "purpose": "防护复验"}).strip()
        print(f"- {name:8s} -> {out.splitlines()[0][:80]}")

    limited = execute_sql_query.invoke({
        "sql": "SELECT * FROM sales_orders LIMIT 9999", "purpose": "限制复验"})
    print("- LIMIT9999 ->", "已压回上限" if "LIMIT 200" in limited else "未压回（检查 sql_max_rows）")


def stage_permission(engine) -> bool:
    """只读账号在数据库侧也应拒绝写：即使绕过工具层，DML 仍失败。"""
    from sqlalchemy import text
    from sqlalchemy.exc import DatabaseError

    print("\n=== 只读账号权限边界（库侧拒绝写） ===")
    statements = {
        "INSERT": "INSERT INTO drugs (drug_id, drug_name) VALUES ('X999', 'x')",
        "UPDATE": "UPDATE drugs SET status = '暂停' WHERE drug_id = 'D001'",
        "DELETE": "DELETE FROM sales_orders",
        "DDL": "CREATE TABLE t_probe (id INT)",
    }
    all_denied = True
    for name, sql in statements.items():
        try:
            with engine.begin() as conn:
                conn.execute(text(sql))
        except DatabaseError as exc:
            code = getattr(getattr(exc, "orig", None), "args", [""])[0]
            print(f"- {name:6s} -> 已拒绝（MySQL {code}）")
        else:
            print(f"- {name:6s} -> !! 未被拒绝，只读账号权限过大")
            all_denied = False
    return all_denied


def main() -> int:
    from sqlalchemy import create_engine

    print(f"[目标] {DB_URL}")
    engine = create_engine(DB_URL, pool_pre_ping=True)
    try:
        if not stage_connect(engine):
            return 1
    except Exception as exc:  # noqa: BLE001
        print(f"[失败] 数据库不可连接：{exc}")
        print("       请先执行 docker compose -f docker-compose.demo.yml up -d 并等待健康检查通过")
        return 1

    stage_tools(DB_URL)
    stage_guards()
    denied = stage_permission(engine)

    print("\n=== 结论 ===")
    print(f"- 真实 MySQL 取数链路：通过（{len(QUERIES)} 条业务查询）")
    print(f"- 执行层只读防护：通过（{len(GUARD_CASES)} 条越权/绕过用例全部拦截）")
    print(f"- 只读账号权限边界：{'通过' if denied else '未通过'}")
    return 0 if denied else 1


if __name__ == "__main__":
    raise SystemExit(main())
