"""调用真实 Embedding，预览正文语义分组。"""
import argparse
import json
import os
from math import isfinite
from pathlib import Path

from dotenv import load_dotenv
from langchain_community.embeddings import DashScopeEmbeddings

from backend.app.semantic_splitter import (
    cosine_similarity,
    group_semantic_units,
    split_semantic_units,
)


def main():
    parser = argparse.ArgumentParser(description="预览语义分组")
    parser.add_argument("--threshold", type=float, required=True)
    args = parser.parse_args()

    if not isfinite(args.threshold) or not -1 <= args.threshold <= 1:
        parser.error("threshold 必须是 -1 到 1 之间的有限数值")

    project_root = Path(__file__).resolve().parents[1]
    load_dotenv(project_root / ".env")

    api_key = os.getenv("DASHSCOPE_API_KEY", "").strip()
    if not api_key:
        raise ValueError("请检查项目根目录 .env 中的 DASHSCOPE_API_KEY")

    model_name = os.getenv("EMBEDDING_MODEL") or "text-embedding-v1"

    # 开发样例，包含转账和贷款两个主题。
    text = (
        "转账前应核对收款人的姓名和账号。"
        "提交转账申请后，可以查询交易状态。"
        "转账成功后可以查看电子回单。"
        "申请个人贷款需要提交收入证明。"
        "贷款审批时会评估申请人的收入和信用情况。"
        "贷款发放后应按照约定按期还款。"
    )

    units = split_semantic_units(text)
    if "".join(units) != text:
        raise ValueError("划分单元后，原文发生变化")

    embeddings = DashScopeEmbeddings(
        model=model_name,
        dashscope_api_key=api_key,
    )

    print("正在获取文本单元的 Embedding...")
    vectors = embeddings.embed_documents(units)

    groups = group_semantic_units(
        units,
        vectors,
        args.threshold,
    )

    if "".join(groups) != text:
        raise ValueError("语义分组后，原文发生变化")

    scores = [
        cosine_similarity(vectors[index - 1], vectors[index])
        for index in range(1, len(units))
    ]

    report = {
        "model": model_name,
        "threshold": args.threshold,
        "units": units,
        "adjacent_scores": scores,
        "groups": groups,
        "text_preserved": "".join(groups) == text,
    }

    target = project_root / "logs" / "semantic_preview.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"model: {model_name}")
    print(f"unit_count: {len(units)}")

    for index, score in enumerate(scores, start=1):
        print(f"{index} -> {index + 1}: {score:.4f}")

    for index, group in enumerate(groups, start=1):
        print(f"\ngroup {index}: {group}")

    print(f"\noutput: {target}")


if __name__ == "__main__":
    main()