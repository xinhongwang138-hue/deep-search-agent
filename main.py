"""应用入口：python main.py 启动后端（默认 8000）。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parent))

from api.server import app  # noqa: E402


def main() -> None:
    host = os.getenv("DS_AGENT_HOST", "0.0.0.0")
    port = int(os.getenv("DS_AGENT_PORT", "8000"))
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
