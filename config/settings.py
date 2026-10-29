"""全局配置。

所有阈值集中在此，禁止散落到提示词或工具实现里，便于按环境调整。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


def _env_str(name: str, default: str = "") -> str:
    value = os.getenv(name)
    return value.strip() if value and value.strip() else default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_path(name: str, default: str) -> Path:
    raw = _env_str(name, default)
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = (PROJECT_ROOT / path).resolve()
    return path


@dataclass(frozen=True)
class Settings:
    # 模型
    model: str = _env_str("DS_AGENT_MODEL", "openai:gpt-4o-mini")
    model_base_url: str = _env_str("DS_AGENT_MODEL_BASE_URL")
    model_api_key: str = _env_str("DS_AGENT_MODEL_API_KEY")
    subagent_model: str = _env_str("DS_AGENT_SUBAGENT_MODEL")

    # 提示词
    prompts_file: Path = PROJECT_ROOT / "prompt" / "prompts.yml"

    # 工作目录
    workspace_root: Path = _env_path("DS_AGENT_WORKSPACE_ROOT", "./workspaces")

    # 检索与取数预算
    max_searches_per_question: int = _env_int("MAX_SEARCHES_PER_QUESTION", 3)
    sql_max_rows: int = _env_int("SQL_MAX_ROWS", 200)
    sql_table_preview_rows: int = _env_int("SQL_TABLE_PREVIEW_ROWS", 100)
    max_sql_fix_attempts: int = _env_int("MAX_SQL_FIX_ATTEMPTS", 1)
    max_file_read_bytes: int = _env_int("MAX_FILE_READ_BYTES", 2 * 1024 * 1024)
    doc_max_pages: int = _env_int("DOC_MAX_PAGES", 200)
    doc_max_rows: int = _env_int("DOC_MAX_ROWS", 30)

    # 外部服务
    tavily_api_key: str = _env_str("TAVILY_API_KEY")
    db_url: str = _env_str("DS_AGENT_DB_URL")
    ragflow_base_url: str = _env_str("RAGFLOW_BASE_URL", "http://127.0.0.1:9380")
    ragflow_api_key: str = _env_str("RAGFLOW_API_KEY")

    # 运行期
    request_timeout: int = field(default=_env_int("REQUEST_TIMEOUT", 60))

    def model_kwargs(self) -> dict[str, str]:
        """返回子智能体可用的 model 覆盖值（空字符串表示沿用主模型）。"""
        return {"model": self.subagent_model} if self.subagent_model else {}


settings = Settings()


def ensure_workspace_root() -> Path:
    settings.workspace_root.mkdir(parents=True, exist_ok=True)
    return settings.workspace_root
