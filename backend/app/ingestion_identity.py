"""为最终片段生成稳定的入库判重标识。"""
import hashlib
import json

from langchain_core.documents import Document


def build_ingestion_key(
    chunk: Document,
    *,
    chunk_size: int,
    chunk_overlap: int,
    embedding_model: str,
    semantic_threshold: float | None,
) -> str:
    """接收已校验的片段和处理配置，不修改输入。"""
    metadata = chunk.metadata

    required_fields = (
        "source",
        "document_id",
        "section_id",
        "chunk_id",
        "splitter_version",
    )

    for field in required_fields:
        value = metadata.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"生成判重标识时缺少有效的 {field}")

    index = metadata.get("chunk_index")
    if type(index) is not int or index < 0:
        raise ValueError("chunk_index 必须为非负整数")

    if not isinstance(embedding_model, str) or not embedding_model.strip():
        raise ValueError("必须提供实际使用的 Embedding 模型标识")

    identity_fields = (
        "source", "file_name", "document_id",
        "section_id", "chunk_id", "chunk_index",
        "parser_version", "splitter_version", "extraction_method",
        "content_type", "heading_path", "article",
        "sheet_name", "page_number", "page_start", "page_end",
        "table_id", "row_start", "row_end",
    )

    payload = {
        "identity_version": "ingestion-v1",
        "metadata": {
            field: metadata.get(field)
            for field in identity_fields
        },
        "content": chunk.page_content,
        "processing": {
            "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap,
            "embedding_model": embedding_model,
            "semantic_threshold": (
                None
                if semantic_threshold is None
                else float(semantic_threshold)
            ),
        },
    }

    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )

    return hashlib.sha256(
        serialized.encode("utf-8")
    ).hexdigest()