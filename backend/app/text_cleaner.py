"""保守清洗文本，保护原文内容和常见 Markdown 结构。"""
import re
from collections import deque
from langchain_core.documents import Document

_BODY_SPACE_TRANSLATION = str.maketrans({
    "\u3000": " ",
    "\u00a0": " ",
})

def clean_text(text: str) -> str:
    # BOM 只在开头作为文件标记处理。
    text = text.removeprefix("\ufeff")

    # 统一 Windows、旧式 Mac 和普通换行。
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    result = []
    fence = ""
    in_indented_code = False

    pending = deque(text.split("\n"))

    while pending:
        line = pending.popleft()
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)

        # 围栏代码块内部原样保留，包括空行和缩进。
        if fence:
            result.append(line)

            if (
                marker
                and marker.group(1)[0] == fence[0]
                and len(marker.group(1)) >= len(fence)
                and not marker.group(2).strip()
            ):
                fence = ""

            continue

        # 记录代码块的开始标记。
        if marker:
            fence = marker.group(1)
            in_indented_code = False
            result.append(line)
            continue

        # 保护四个空格或 Tab 开始的缩进代码。
        if line.startswith(("    ", "\t")):
            in_indented_code = True
        elif line.strip():
            in_indented_code = False

        if in_indented_code:
            result.append(line)
            continue

        # 含反引号的行整体保留，保护行内代码。
        if "`" in line:
            result.append(line)
            continue

        # 换页符和垂直制表符保留为文本边界。
        separated = line.replace("\f", "\n\n").replace("\v", "\n")
        parts = separated.split("\n")

        if len(parts) > 1:
            pending.extendleft(reversed(parts))
            continue

        # 使用空格分隔，避免直接删除后粘连文字。
        normalized = line.replace("\x00", " ")

        if normalized != line:
            pending.appendleft(normalized)
            continue

        # 分别保留行首空白、正文、行尾空白。
        spacing = re.fullmatch(r"(\s*)(.*?)(\s*)", line)

        if spacing:
            normalized = (
                spacing.group(1)
                + spacing.group(2).translate(_BODY_SPACE_TRANSLATION)
                + spacing.group(3)
            )

            if normalized != line:
                pending.appendleft(normalized)
                continue

        # 普通正文连续多个空白行，最多保留一个。
        if not line.strip():
            line = ""
            if result and result[-1] == "":
                continue

        result.append(line)

    cleaned = "\n".join(result)

    # 保留段尾的一个空行，避免 Word 相邻段落失去分隔。
    if text.endswith("\n\n") and cleaned and not cleaned.endswith("\n\n"):
        cleaned += "\n"

    return cleaned

def _clean_cell(value) -> str:
    """空单元格保持为空，其他值按文本清洗。"""
    return clean_text("" if value is None else str(value))


def clean_documents(documents: list[Document]) -> list[Document]:
    """清洗正文与结构化表格，返回新的 Document。"""
    cleaned_documents = []

    for doc in documents:
        metadata = dict(doc.metadata)

        if metadata.get("content_type") == "table":
            table_data = metadata.get("table_data")

            if table_data is None:
                raise ValueError("表格缺少表头和数据行")

            headers = [
                _clean_cell(value)
                for value in table_data["headers"]
            ]
            rows = [
                [_clean_cell(value) for value in row]
                for row in table_data["rows"]
            ]

            # 创建新的字典和列表，保留原始对象。
            metadata["table_data"] = {
                **table_data,
                "headers": headers,
                "rows": rows,
            }

            for key in ("table_title", "table_note"):
                value = metadata.get(key)
                if isinstance(value, str):
                    metadata[key] = clean_text(value)

            # 临时文本表示；最终 Markdown 仍由 TableSplitter 生成。
            content = "\n".join(
                "\t".join(row)
                for row in [headers, *rows]
            )

        else:
            content = clean_text(doc.page_content)

            # 只过滤清洗后没有正文的文本 Document。
            if not content.strip():
                continue

        cleaned_documents.append(Document(
            page_content=content,
            metadata=metadata,
        ))

    return cleaned_documents