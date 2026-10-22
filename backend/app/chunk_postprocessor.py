"""检查最终片段，不改写有效正文。"""
import logging

from langchain_core.documents import Document


logger = logging.getLogger(__name__)


def postprocess_chunks(
    chunks: list[Document],
    max_chars: int,
) -> list[Document]:
    if type(max_chars) is not int or max_chars <= 0:
        raise ValueError("max_chars 必须为正整数")

    result = []
    empty_count = 0

    required_fields = (
        "document_id",
        "section_id",
        "chunk_id",
        "splitter_version",
    )

    for number, chunk in enumerate(chunks, start=1):
        content = chunk.page_content

        if not content.strip():
            empty_count += 1
            continue

        metadata = chunk.metadata

        for field in required_fields:
            value = metadata.get(field)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"第 {number} 个片段缺少有效的 {field}"
                )

        chunk_index = metadata.get("chunk_index")
        if type(chunk_index) is not int or chunk_index < 0:
            raise ValueError(
                f"第 {number} 个片段的 chunk_index "
                "必须为非负整数"
            )

        if len(content) > max_chars:
            is_table = metadata.get("content_type") == "table"

            if not is_table:
                raise ValueError(
                    f"第 {number} 个片段是超长正文，"
                    "请检查长度兜底"
                )

            if metadata.get("oversized") is not True:
                raise ValueError(
                    f"第 {number} 个片段是超长表格，"
                    "但未标记 oversized"
                )

        result.append(chunk)

    logger.info(
        "后处理：保留 %s 个片段，跳过 %s 个空白片段",
        len(result),
        empty_count,
    )
    return result