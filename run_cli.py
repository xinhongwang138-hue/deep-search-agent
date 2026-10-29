"""命令行入口。

用法：
    python run_cli.py --question "结合内部论文分析 2025 年 AI 药物研发趋势"
    python run_cli.py            # 交互模式
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 保证以脚本方式运行时能导入项目内模块
sys.path.insert(0, str(Path(__file__).resolve().parent))

from agent.main_agent import run  # noqa: E402


def _print_result(result: dict) -> None:
    print("\n" + "=" * 60)
    print(result["answer"] or "（模型未返回文本内容，请检查日志与工具调用结果）")
    print("=" * 60)
    print(f"会话目录：{result['workspace']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Deep Search Agent 命令行")
    parser.add_argument("--question", "-q", help="要检索的问题")
    parser.add_argument("--session-id", "-s", help="复用已有会话 id")
    args = parser.parse_args()

    if args.question:
        _print_result(run(args.question, args.session_id))
        return 0

    print("进入交互模式，输入问题后回车执行；输入 exit 退出。")
    while True:
        try:
            question = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not question:
            continue
        if question.lower() in {"exit", "quit", "q"}:
            return 0
        try:
            _print_result(run(question, args.session_id))
        except Exception as exc:  # 单轮失败不退出会话
            print(f"执行失败：{type(exc).__name__}: {exc}")


if __name__ == "__main__":
    raise SystemExit(main())
