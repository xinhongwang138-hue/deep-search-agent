"""会话工作目录管理：建目录、拼运行期上下文。"""
from __future__ import annotations

import uuid
from pathlib import Path

from tools.path_guard import create_session_workspace, list_uploads


def new_session_id() -> str:
    return uuid.uuid4().hex[:12]


def prepare_session(session_id: str | None = None) -> tuple[str, Path]:
    """创建并绑定会话工作目录，返回 (session_id, 绝对路径)。"""
    sid = session_id or new_session_id()
    path = create_session_workspace(sid)
    return sid, path


def build_user_message(question: str, workspace: Path) -> str:
    """把工作目录与上传清单拼进用户消息，符合提示词中的运行期上下文约定。"""
    uploads = list_uploads()
    upload_hint = "无" if not uploads else "、".join(uploads)
    return (
        f"{question.strip()}\n\n"
        f"---\n"
        f"运行期上下文：\n"
        f"- 会话工作目录：{workspace}\n"
        f"- 上传文件：{upload_hint}"
    )
