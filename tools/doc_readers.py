"""多格式文档解析后端（PDF / DOCX / XLSX）。

职责单一：把落盘文件变成可读文本。路径沙箱、文件大小上限由调用方
（tools/file_tools.py）负责，本模块不做任何路径判断。

设计约束：
1. 任何异常都在这里收敛为可读文本，绝不向上抛，避免工具调用链中断；
2. 页数 / 行数 / 字符数三重上限，防止单个文件把上下文撑爆；
3. 缺依赖时给出明确安装指引，而不是抛 ModuleNotFoundError。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

_TRUNCATED = "\n…（内容已截断）"


def _missing(pkg: str, extra: str = "doc") -> str:
    return f"读取失败：缺少 {pkg} 依赖，请执行 pip install {pkg}（或 uv sync --extra {extra}）。"


def read_pdf(path: Path, max_chars: int, max_pages: int = 200) -> str:
    """提取 PDF 文本，按页打标，便于回答时标注页码。"""
    try:
        from pypdf import PdfReader
    except ModuleNotFoundError:
        return _missing("pypdf")

    try:
        reader = PdfReader(str(path))
    except Exception as exc:  # 损坏 / 加密 / 非 PDF
        return f"PDF 解析失败：{type(exc).__name__}: {exc}"

    try:
        total = len(reader.pages)
    except Exception as exc:
        return f"PDF 解析失败：{type(exc).__name__}: {exc}"

    pages_limit = min(total, max(1, max_pages))
    blocks: list[str] = []
    used = 0
    empty_pages = 0

    for idx in range(pages_limit):
        try:
            page_text = (reader.pages[idx].extract_text() or "").strip()
        except Exception as exc:
            page_text = f"[第 {idx + 1} 页解析失败：{type(exc).__name__}]"
        if not page_text:
            empty_pages += 1
            continue
        block = f"\n[第 {idx + 1} 页]\n{page_text}"
        blocks.append(block)
        used += len(block)
        if used >= max_chars:
            break

    if not blocks:
        return (
            f"PDF 共 {total} 页，但未提取到文本：大概率是扫描件或图片型 PDF，"
            "需要 OCR 才能读取，请改用可复制文本的版本。"
        )

    header = f"PDF 共 {total} 页，已解析 {len(blocks)} 页有文本"
    if total > pages_limit:
        header += f"（仅取前 {pages_limit} 页）"
    if empty_pages:
        header += f"，{empty_pages} 页无文本层"
    body = "".join(blocks)
    truncated = len(body) > max_chars
    return header + "：\n" + body[:max_chars] + (_TRUNCATED if truncated else "")


def read_docx(path: Path, max_chars: int, max_table_rows: int = 50) -> str:
    """提取 DOCX 正文段落与表格（表格转 Markdown 便于引用）。"""
    try:
        import docx
    except ModuleNotFoundError:
        return _missing("python-docx")

    try:
        document = docx.Document(str(path))
    except Exception as exc:
        return f"DOCX 解析失败：{type(exc).__name__}: {exc}"

    parts: list[str] = []
    paragraph_count = 0
    for para in document.paragraphs:
        text = (para.text or "").strip()
        if text:
            parts.append(text)
            paragraph_count += 1

    table_count = 0
    for t_idx, table in enumerate(document.tables, start=1):
        rows: list[str] = []
        for r_idx, row in enumerate(table.rows):
            if r_idx >= max_table_rows:
                rows.append(f"…（表 {t_idx} 仅取前 {max_table_rows} 行）")
                break
            cells = [(cell.text or "").strip().replace("\n", " ") for cell in row.cells]
            rows.append("| " + " | ".join(cells) + " |")
            if r_idx == 0:
                rows.append("| " + " | ".join("---" for _ in cells) + " |")
        if rows:
            table_count += 1
            parts.append(f"\n[表 {t_idx}]")
            parts.extend(rows)

    if not parts:
        return "DOCX 未提取到文本内容（文档可能只有图片或嵌入对象）。"

    body = "\n".join(parts)
    header = f"DOCX 共 {paragraph_count} 段正文、{table_count} 张表格"
    truncated = len(body) > max_chars
    return header + "：\n" + body[:max_chars] + (_TRUNCATED if truncated else "")


def _fmt_number(value: float) -> str:
    """金额/数量按人类可读输出，避免 1.04137e+06 这类科学计数法。"""
    if isinstance(value, int):
        return str(value)
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.4f}".rstrip("0").rstrip(".")


def _numeric_stats(rows: list[tuple[Any, ...]], header: list[str], col: int) -> str:
    """对单个数值列做简易统计，替代 pandas.describe 的轻量实现。"""
    values = [
        row[col]
        for row in rows[1:]
        if col < len(row) and isinstance(row[col], (int, float)) and not isinstance(row[col], bool)
    ]
    if not values:
        return ""
    name = header[col] if col < len(header) else f"col{col}"
    total = sum(values)
    average = round(total / len(values), 4)
    return (
        f"{name}: 非空 {len(values)}，最小 {_fmt_number(min(values))}，"
        f"最大 {_fmt_number(max(values))}，合计 {_fmt_number(total)}，"
        f"均值 {_fmt_number(average)}"
    )


def read_xlsx(path: Path, max_chars: int, max_rows: int = 30) -> str:
    """逐个工作表输出列名、前 N 行与数值列统计。"""
    try:
        from openpyxl import load_workbook
    except ModuleNotFoundError:
        return _missing("openpyxl")

    try:
        workbook = load_workbook(str(path), read_only=True, data_only=True)
    except Exception as exc:
        return f"XLSX 解析失败：{type(exc).__name__}: {exc}"

    parts: list[str] = []
    try:
        for sheet in workbook.worksheets:
            collected: list[tuple[Any, ...]] = []
            for row in sheet.iter_rows(values_only=True):
                collected.append(row)
                if len(collected) > max_rows:
                    break

            if not collected or all(all(cell is None for cell in row) for row in collected):
                parts.append(f"\n[工作表 {sheet.title}] 空表")
                continue

            header = [
                "" if cell is None else str(cell).strip() for cell in collected[0]
            ]
            width = max((len(row) for row in collected), default=0)
            header += [f"col{i + 1}" for i in range(len(header), width)]

            lines = [f"\n[工作表 {sheet.title}] 列名：{', '.join(h for h in header if h)}"]
            preview = collected[:max_rows]
            lines.append("| " + " | ".join(header) + " |")
            lines.append("| " + " | ".join("---" for _ in header) + " |")
            for row in preview[1:]:
                cells = [("" if cell is None else str(cell).replace("\n", " ")) for cell in row]
                cells += [""] * (len(header) - len(cells))
                lines.append("| " + " | ".join(cells) + " |")
            if len(collected) > max_rows:
                lines.append(f"…（仅取前 {max_rows} 行）")

            stats = [s for s in (_numeric_stats(preview, header, i) for i in range(len(header))) if s]
            if stats:
                lines.append("[数值列统计]")
                lines.extend(stats)
            parts.append("\n".join(lines))
    finally:
        workbook.close()

    if not parts:
        return "XLSX 中没有任何工作表。"

    body = "".join(parts)
    truncated = len(body) > max_chars
    return "XLSX 解析结果：\n" + body[:max_chars] + (_TRUNCATED if truncated else "")
