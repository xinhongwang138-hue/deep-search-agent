"""离线自检：不依赖 MySQL / 大模型，用 SQLite 复刻 cps_demo 三表，验证取数链路与只读防护。

用法：
    uv run python scripts/verify_offline.py
"""
from __future__ import annotations

import os
import re
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = Path(tempfile.gettempdir()) / "cps_demo_verify.db"

DDL = """
CREATE TABLE drugs (drug_id TEXT PRIMARY KEY, drug_name TEXT, generic_name TEXT, category TEXT,
  spec TEXT, manufacturer TEXT, approval_no TEXT, unit_price REAL, is_prescription INTEGER,
  status TEXT, created_at TEXT);
CREATE TABLE inventory (inventory_id INTEGER PRIMARY KEY AUTOINCREMENT, drug_id TEXT, warehouse TEXT,
  batch_no TEXT, quantity INTEGER, safety_stock INTEGER, expiry_date TEXT, updated_at TEXT);
CREATE TABLE sales_orders (order_id INTEGER PRIMARY KEY, drug_id TEXT, customer_type TEXT, region TEXT,
  quantity INTEGER, unit_price REAL, amount REAL, order_date TEXT, salesperson TEXT);
"""


def build_db() -> None:
    if DB.exists():
        DB.unlink()
    seed = (ROOT / "sql" / "seed.sql").read_text(encoding="utf-8")
    conn = sqlite3.connect(DB)
    conn.executescript(DDL)
    for table in ("drugs", "inventory", "sales_orders"):
        block = re.search("INSERT INTO " + table + r"\s*\((.*?)\)\s*VALUES(.*?);", seed, re.S)
        if not block:
            raise SystemExit(f"seed.sql 缺少 {table} 的 INSERT 语句")
        conn.execute(f"INSERT INTO {table} ({block.group(1)}) VALUES {block.group(2).strip()}")
    conn.commit()
    counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in
              ("drugs", "inventory", "sales_orders")}
    conn.close()
    print("[db]", counts)


def main() -> int:
    build_db()
    os.environ["DS_AGENT_DB_URL"] = "sqlite:///" + str(DB).replace("\\", "/")
    sys.path.insert(0, str(ROOT))

    from tools.sql_tools import execute_sql_query, get_table_data, list_sql_tables

    print("\n=== list_sql_tables ===")
    print(list_sql_tables.invoke({}))

    print("\n=== get_table_data('drugs') ===")
    print(get_table_data.invoke({"table_name": "drugs"})[:300])

    print("\n=== Top5 药品按 GMV ===")
    print(execute_sql_query.invoke({
        "sql": "SELECT d.drug_name, SUM(s.amount) AS gmv FROM sales_orders s "
               "JOIN drugs d ON d.drug_id = s.drug_id GROUP BY d.drug_name ORDER BY gmv DESC LIMIT 5",
        "purpose": "找出销售额 Top5 药品",
    }))

    print("\n=== 防护复验（应全部被拒或收紧） ===")
    cases = {
        "DELETE": "DELETE FROM sales_orders",
        "多语句": "SELECT 1; DROP TABLE drugs",
        "注释": "SELECT 1 -- x",
        "SET": "SET @a = 1",
    }
    for name, sql in cases.items():
        out = execute_sql_query.invoke({"sql": sql, "purpose": "防护复验"}).strip()
        print(f"- {name:6s} -> {out.splitlines()[0][:70]}")

    limited = execute_sql_query.invoke({
        "sql": "SELECT * FROM sales_orders LIMIT 9999", "purpose": "限制复验"})
    print("- LIMIT9999 ->", "已压回上限" if "LIMIT 200" in limited else "未压回（检查 sql_max_rows）")
    print("\n自检完成。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
