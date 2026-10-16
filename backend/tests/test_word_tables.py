import unittest
from pathlib import Path

from backend.app.document_loader import DocumentLoader
from backend.app.document_splitter import StructuredDocumentSplitter


class WordTableTests(unittest.TestCase):
    def test_word_text_and_table_keep_order_and_headings(self):
        project_root = Path(__file__).resolve().parents[2]
        sample = project_root / "data" / "samples" / "bank_word_demo.docx"

        documents = DocumentLoader().load_single_file(str(sample))
        chunks = StructuredDocumentSplitter().split_documents(documents)

        # 正文、表格、表后正文的顺序保持正确。
        self.assertEqual(
            [chunk.metadata["content_type"] for chunk in chunks],
            ["text", "table", "text"],
        )

        # 所有片段都继承两级标题。
        expected_headings = ["第一章 转账规则", "第一节 申请材料"]
        for chunk in chunks:
            self.assertEqual(chunk.metadata["heading_path"], expected_headings)

        self.assertIn("办理转账前请核对以下材料。", chunks[0].page_content)
        self.assertIn("材料不完整时，应先补充材料。", chunks[2].page_content)

        # 表头、两条完整记录和行范围都保留下来。
        table = chunks[1]
        self.assertIn("| 编号 | 材料 |", table.page_content)
        self.assertIn("| 001 | 有效身份证件 |", table.page_content)
        self.assertIn("| 002 | 资金用途说明 |", table.page_content)
        self.assertEqual(
            (table.metadata["row_start"], table.metadata["row_end"]),
            (1, 2),
        )


if __name__ == "__main__":
    unittest.main()