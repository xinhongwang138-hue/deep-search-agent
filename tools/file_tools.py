"""文档生成工具（仅主智能体可用）。

写入位置固定在会话工作目录的 output/ 下，返回相对路径；
PDF 导出走多后端回退，全部不可用时明确报错，绝不产出空文件。
"""
from __future__ import annotations

import datetime as _dt
from pathlib import Path

from langchain_core.tools import tool

from config.settings import settings
from tools.doc_readers import read_docx, read_pdf, read_xlsx
from tools.path_guard import (
    list_uploads,
    max_read_bytes,
    relative_to_workspace,
    resolve_in_workspace,
    slugify,
)


def _output_dir() -> Path:
    out = resolve_in_workspace("output")
    out.mkdir(parents=True, exist_ok=True)
    return out


def _unique_path(directory: Path, stem: str, suffix: str) -> Path:
    candidate = directory / f"{stem}{suffix}"
    if not candidate.exists():
        return candidate
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    return directory / f"{stem}_{stamp}{suffix}"


@tool
def generate_markdown(title: str, body: str) -> str:
    """把已完成的内容写成 Markdown 文档，保存到当前会话的输出目录。

    只能在信息收集完成后调用，正文中不得出现占位符。

    Args:
        title: 文档标题，同时作为文件名。
        body: 完整正文（Markdown 格式，不含标题行）。
    """
    if not body or not body.strip():
        return "生成失败：正文为空，请先完成信息收集再生成文档。"

    for placeholder in ("此处待补充", "（略）", "TODO", "等待子任务完成"):
        if placeholder in body:
            return f"生成失败：正文仍包含占位内容「{placeholder}」，请补齐后再生成。"

    stamp = _dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    meta = f"# {title}\n\n> 生成时间：{stamp}\n\n"
    path = _unique_path(_output_dir(), slugify(title), ".md")
    path.write_text(meta + body.strip() + "\n", encoding="utf-8")
    return f"已生成 Markdown 文档：{relative_to_workspace(path)}"


def _md_to_html(markdown_text: str) -> str | None:
    try:
        import markdown as md
    except ModuleNotFoundError:
        return None
    return md.markdown(markdown_text, extensions=["tables", "fenced_code", "toc"])


@tool
def convert_md_to_pdf(markdown_file: str) -> str:
    """把已生成的 Markdown 文档转换为 PDF，保存到同一输出目录。

    Args:
        markdown_file: generate_markdown 返回的相对路径或文件名。
    """
    try:
        md_path = resolve_in_workspace(markdown_file, must_exist=True)
    except (FileNotFoundError, PermissionError) as exc:
        return f"转换失败：{exc}"

    pdf_path = md_path.with_suffix(".pdf")
    text = md_path.read_text(encoding="utf-8")
    html = _md_to_html(text)

    # 后端 1：weasyprint（HTML → PDF）
    if html:
        try:
            from weasyprint import HTML  # type: ignore

            HTML(string=html).write_pdf(str(pdf_path))
            return f"已生成 PDF 文档：{relative_to_workspace(pdf_path)}"
        except ModuleNotFoundError:
            pass
        except Exception as exc:
            return f"PDF 转换失败（weasyprint）：{type(exc).__name__}: {exc}"

    # 后端 2：pandoc（需要本机安装 pandoc 可执行文件）
    try:
        import pypandoc  # type: ignore

        pypandoc.convert_file(str(md_path), "pdf", outputfile=str(pdf_path))
        return f"已生成 PDF 文档：{relative_to_workspace(pdf_path)}"
    except ModuleNotFoundError:
        pass
    except Exception as exc:
        return f"PDF 转换失败（pandoc）：{type(exc).__name__}: {exc}"

    return (
        "PDF 转换失败：未检测到可用后端。请安装 weasyprint 或 pypandoc+pandoc 后重试；"
        "Markdown 文档已正常生成，可在报告中说明该限制。"
    )


_TEXT_SUFFIX = {
    ".md", ".markdown", ".txt", ".json", ".csv", ".yaml", ".yml",
    ".log", ".sql", ".py", ".html", ".xml", ".ini", ".conf",
}


@tool
def read_file_content(filename: str, max_chars: int = 20000) -> str:
    """读取当前会话目录内的文件内容，用于核对用户上传的材料。

    支持纯文本（md/txt/json/csv/yaml/log/代码等）、PDF、Word（.docx）、
    Excel（.xlsx）；PDF 按页打标，Excel 给出列名、前若干行与数值列统计。
    路径必须落在当前会话工作目录内，越界直接拒绝。

    Args:
        filename: 上传文件名或相对路径。
        max_chars: 最多返回的字符数。
    """
    try:
        path = resolve_in_workspace(filename, must_exist=True)
    except (FileNotFoundError, PermissionError) as exc:
        return f"读取失败：{exc}\n当前可读文件：{list_uploads() or '无上传文件'}"

    size = path.stat().st_size
    if size > max_read_bytes():
        return f"读取失败：文件大小 {size} 字节，超过上限 {max_read_bytes()} 字节。"

    suffix = path.suffix.lower()
    limit = max(1000, int(max_chars))

    if suffix in _TEXT_SUFFIX:
        content = path.read_text(encoding="utf-8", errors="replace")
        if len(content) > limit:
            return content[:limit] + "\n…（内容已截断）"
        return content

    if suffix == ".pdf":
        return read_pdf(path, limit, max_pages=settings.doc_max_pages)

    if suffix == ".docx":
        return read_docx(path, limit, max_table_rows=settings.doc_max_rows)

    if suffix in {".xlsx", ".xlsm"}:
        return read_xlsx(path, limit, max_rows=settings.doc_max_rows)

    if suffix == ".xls":
        return (
            "读取失败：旧版 .xls 二进制格式不支持，请另存为 .xlsx 后重新上传。"
        )

    return (
        f"暂不支持直接解析 {suffix or '（无扩展名）'} 类型文件。"
        "当前支持：文本类（.md/.txt/.json/.csv/.yaml/.log/代码）、.pdf、.docx、.xlsx。"
        "请先转换格式，或在回答中说明依据的是该文件名而非其内容。"
    )
