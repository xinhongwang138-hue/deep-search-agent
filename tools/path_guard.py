"""会话工作目录沙箱。

提示词里写的"禁止 ../"只是声明，真正的防护在这里：
所有文件读写都必须经过 resolve_in_workspace()，解析符号链接与相对路径后
再做父子关系校验，越界直接抛 WorkspaceViolation。
"""
from __future__ import annotations

import re
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Iterator

from config.settings import settings, ensure_workspace_root

_workspace: ContextVar[Path | None] = ContextVar("ds_workspace", default=None)

_UNSAFE_NAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


class WorkspaceViolation(PermissionError):
    """访问越界：目标不在当前会话工作目录内。"""


def slugify(text: str, *, max_length: int = 40) -> str:
    """把标题转换为安全文件名片段（保留中文）。"""
    cleaned = _UNSAFE_NAME.sub("_", text).strip().strip(".")
    cleaned = re.sub(r"\s+", "_", cleaned)
    return cleaned[:max_length] or "document"


def create_session_workspace(session_id: str) -> Path:
    """创建 session_{id}/{uploads,output} 并绑定为当前上下文。"""
    root = ensure_workspace_root()
    safe_id = slugify(session_id, max_length=64)
    session_dir = root / f"session_{safe_id}"
    for sub in ("uploads", "output"):
        (session_dir / sub).mkdir(parents=True, exist_ok=True)
    _workspace.set(session_dir.resolve())
    return session_dir.resolve()


def current_workspace() -> Path:
    path = _workspace.get()
    if path is None:
        raise WorkspaceViolation("当前上下文未绑定会话工作目录，请先调用 create_session_workspace()")
    return path


@contextmanager
def use_workspace(path: Path) -> Iterator[Path]:
    token = _workspace.set(Path(path).resolve())
    try:
        yield current_workspace()
    finally:
        _workspace.reset(token)


def resolve_in_workspace(target: str | Path, *, must_exist: bool = False) -> Path:
    """把用户/模型给的文件名解析为工作目录内的绝对路径，越界即抛错。"""
    root = current_workspace()
    candidate = Path(target)
    resolved = (candidate if candidate.is_absolute() else root / candidate).resolve()

    if resolved != root and root not in resolved.parents:
        raise WorkspaceViolation(f"禁止访问工作目录之外的路径：{target}")

    if must_exist and not resolved.exists():
        raise FileNotFoundError(f"文件不存在：{target}")
    return resolved


def relative_to_workspace(path: Path) -> str:
    """对外只暴露相对路径，避免泄露服务器目录结构。"""
    try:
        return path.resolve().relative_to(current_workspace()).as_posix()
    except ValueError:
        return path.name


def list_uploads() -> list[str]:
    """当前会话上传文件清单（相对路径），用于拼进用户消息。"""
    uploads = current_workspace() / "uploads"
    if not uploads.exists():
        return []
    return sorted(p.name for p in uploads.iterdir() if p.is_file())


def max_read_bytes() -> int:
    return settings.max_file_read_bytes
