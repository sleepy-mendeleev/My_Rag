"""Inspect parsing and splitting without Milvus, embedding, or LLM calls."""
import argparse
import json
from pathlib import Path
from backend.app.document_loader import DocumentLoader
from backend.app.document_splitter import StructuredDocumentSplitter


def main():
    parser = argparse.ArgumentParser(description='预览文档结构，无需连接数据库或模型')
    parser.add_argument('file')
    parser.add_argument('--output', default='logs/document_preview.json')
    args = parser.parse_args()
    documents = DocumentLoader().load_single_file(args.file)
    chunks = StructuredDocumentSplitter().split_documents(documents)
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps([{'content': doc.page_content, 'metadata': doc.metadata}
                                 for doc in chunks], ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'解析 {len(documents)} 个原始文档，切分为 {len(chunks)} 个片段。')
    print(f'预览文件：{target.resolve()}')


if __name__ == '__main__':
    main()
