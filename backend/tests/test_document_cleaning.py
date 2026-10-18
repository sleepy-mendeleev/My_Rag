import hashlib
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from langchain_core.documents import Document

from backend.app.document_loader import DocumentLoader
from backend.app.text_cleaner import clean_documents


class DocumentCleaningTests(unittest.TestCase):
    def test_text_cleaning_preserves_input_and_metadata(self):
        original = "\ufeff客户\x00办理\n\n\n材料\u3000完整\n\n"
        source = Document(
            page_content=original,
            metadata={
                "source": "D:/资料/业务\u3000规则.docx",
                "file_type": "docx",
            },
        )
        empty = Document(page_content=" \n\x00")

        result = clean_documents([source, empty])

        self.assertEqual(len(result), 1)
        self.assertEqual(
            result[0].page_content,
            "客户 办理\n\n材料 完整\n\n",
        )
        self.assertEqual(result[0].metadata, source.metadata)
        self.assertEqual(source.page_content, original)

    def test_table_structure_and_original_values_are_preserved(self):
        source = Document(
            page_content="临时表格文本",
            metadata={
                "content_type": "table",
                "source": "sample.csv",
                "table_title": "表1\u3000材料",
                "table_note": "注：材料\u00a0完整",
                "table_data": {
                    "headers": ["产品\u3000编号", "材料"],
                    "rows": [
                        ["001", ""],
                        ["", ""],
                        ["002", "材料\u3000完整"],
                    ],
                },
            },
        )
        original_metadata = deepcopy(source.metadata)

        result = clean_documents([source])[0]

        self.assertEqual(result.metadata["table_data"], {
            "headers": ["产品 编号", "材料"],
            "rows": [
                ["001", ""],
                ["", ""],
                ["002", "材料 完整"],
            ],
        })
        self.assertEqual(result.metadata["table_title"], "表1 材料")
        self.assertEqual(result.metadata["table_note"], "注：材料 完整")
        self.assertEqual(source.metadata, original_metadata)

    def test_table_without_structure_raises(self):
        source = Document(
            page_content="缺少结构",
            metadata={"content_type": "table"},
        )

        with self.assertRaisesRegex(ValueError, "表格缺少"):
            clean_documents([source])

    def test_loader_applies_cleaning_and_keeps_original_file_hash(self):
        raw = (
            "\ufeff客户\x00办理\r\n\r\n\r\n"
            "原则上不得超过50万元。"
        ).encode("utf-8")

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.txt"
            path.write_bytes(raw)

            documents = DocumentLoader().load_single_file(str(path))

        self.assertEqual(len(documents), 1)
        self.assertEqual(
            documents[0].page_content,
            "客户 办理\n\n原则上不得超过50万元。",
        )
        self.assertEqual(
            documents[0].metadata["document_id"],
            hashlib.sha256(raw).hexdigest(),
        )


if __name__ == "__main__":
    unittest.main()