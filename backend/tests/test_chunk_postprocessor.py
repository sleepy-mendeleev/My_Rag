import unittest
from unittest.mock import Mock

from langchain_core.documents import Document

from backend.app.chunk_postprocessor import postprocess_chunks
from backend.app.vector_db_manager import VectorDatabaseManager


class ChunkPostprocessorTests(unittest.TestCase):
    @staticmethod
    def chunk(text, **metadata):
        fields = {
            "source": "demo.txt",
            "document_id": "doc-1",
            "section_id": "section-1",
            "chunk_id": "chunk-1",
            "chunk_index": 0,
            "splitter_version": "structure-v2",
            "content_type": "text",
        }
        fields.update(metadata)
        return Document(page_content=text, metadata=fields)

    def test_preserves_short_clause_and_original_text(self):
        short = self.chunk("正常办理。")
        spaced = self.chunk(
            "  保留原有空格。\n",
            chunk_id="chunk-2",
            chunk_index=1,
        )

        result = postprocess_chunks([short, spaced], 50)

        self.assertEqual(len(result), 2)
        self.assertIs(result[0], short)
        self.assertIs(result[1], spaced)
        self.assertEqual(
            result[1].page_content,
            "  保留原有空格。\n",
        )

    def test_discards_only_blank_chunks(self):
        blank = Document(page_content=" \n\t")
        valid = self.chunk("有效正文。")

        result = postprocess_chunks([blank, valid], 50)

        self.assertEqual(result, [valid])

    def test_rejects_missing_identity_and_oversized_text(self):
        incomplete = self.chunk("有效正文。")
        incomplete.metadata.pop("chunk_id")

        with self.assertRaisesRegex(ValueError, "chunk_id"):
            postprocess_chunks([incomplete], 50)

        with self.assertRaisesRegex(ValueError, "超长正文"):
            postprocess_chunks(
                [self.chunk("甲" * 51)],
                50,
            )

    def test_preserves_flagged_oversized_table(self):
        table = self.chunk(
            "| " + "材料" * 40 + " |",
            content_type="table",
            splitter_version="table-v1",
            oversized=True,
        )

        result = postprocess_chunks([table], 50)
        self.assertIs(result[0], table)

        table.metadata["oversized"] = False

        with self.assertRaisesRegex(ValueError, "oversized"):
            postprocess_chunks([table], 50)

    def test_empty_split_result_cannot_report_upload_success(self):
        manager = VectorDatabaseManager.__new__(
            VectorDatabaseManager
        )
        manager.load_document = Mock(
            return_value=[Document(page_content="# 只有标题")]
        )
        manager.split_documents = Mock(return_value=[])
        manager.add_documents_to_db = Mock()

        with self.assertLogs(
            "backend.app.vector_db_manager",
            level="ERROR",
        ):
            with self.assertRaisesRegex(ValueError, "有效片段"):
                manager.process_file("demo.txt")

        manager.add_documents_to_db.assert_not_called()