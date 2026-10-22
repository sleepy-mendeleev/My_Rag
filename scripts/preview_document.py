"""预览文件解析和切分；语义模式会调用真实 Embedding 模型。"""
import argparse
import json
import os
from collections import Counter
from math import isfinite
from pathlib import Path

from dotenv import load_dotenv

from backend.app.document_loader import DocumentLoader
from backend.app.document_splitter import StructuredDocumentSplitter


def main():
    parser = argparse.ArgumentParser(
        description="预览文档结构与切分结果"
    )
    parser.add_argument("file")
    parser.add_argument("--output")
    parser.add_argument(
        "--semantic",
        action="store_true",
        help="启用真实 Embedding 语义切分",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        help="语义切分的相似度阈值",
    )
    args = parser.parse_args()

    if args.semantic:
        if (
            args.threshold is None
            or not isfinite(args.threshold)
            or not -1 <= args.threshold <= 1
        ):
            parser.error(
                "语义模式必须提供 --threshold，"
                "且阈值是 -1 到 1 之间的有限数值"
            )
    elif args.threshold is not None:
        parser.error("--threshold 需要与 --semantic 一起使用")

    project_root = Path(__file__).resolve().parents[1]

    # 两种模式使用同一套文件解析流程。
    documents = DocumentLoader().load_single_file(args.file)

    embeddings = None

    if args.semantic:
        from langchain_community.embeddings import DashScopeEmbeddings

        load_dotenv(project_root / ".env")

        api_key = os.getenv("DASHSCOPE_API_KEY", "").strip()
        if not api_key:
            raise ValueError(
                "请检查项目根目录 .env 中的 DASHSCOPE_API_KEY"
            )

        model_name = (
            os.getenv("EMBEDDING_MODEL", "").strip()
            or "text-embedding-v1"
        )

        embeddings = DashScopeEmbeddings(
            model=model_name,
            dashscope_api_key=api_key,
        )

        print(f"Embedding 模型：{model_name}")
        print(f"语义阈值：{args.threshold}")

    splitter = StructuredDocumentSplitter(
        embeddings=embeddings,
        semantic_threshold=args.threshold,
    )
    chunks = splitter.split_documents(documents)

    if args.output:
        target = Path(args.output)
    else:
        filename = (
            "document_semantic_preview.json"
            if args.semantic
            else "document_preview.json"
        )
        target = project_root / "logs" / filename

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(
            [
                {
                    "content": chunk.page_content,
                    "metadata": chunk.metadata,
                }
                for chunk in chunks
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    versions = Counter(
        chunk.metadata.get("splitter_version", "unknown")
        for chunk in chunks
    )

    print(f"原始 Document 数量：{len(documents)}")
    print(f"最终 chunk 数量：{len(chunks)}")

    for version, count in sorted(versions.items()):
        print(f"{version}: {count}")

    print(f"预览文件：{target.resolve()}")


if __name__ == "__main__":
    main()
