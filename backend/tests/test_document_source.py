import unittest
from unittest.mock import Mock

from langchain_core.documents import Document

from backend.app.document_splitter import StructuredDocumentSplitter
from backend.app.vector_db_manager import VectorDatabaseManager


class DocumentSourceTests(unittest.TestCase):
    @staticmethod
    def document(path, text="办理前核对材料。", **metadata):
        fields = {
            "source": path,
            "file_name": "document.txt",
            "document_id": "same-content-hash",
            "content_type": "text",
        }
        fields.update(metadata)

        return Document(
            page_content=text,
            metadata=fields,
        )

    @staticmethod
    def manager_for(batches):
        manager = VectorDatabaseManager.__new__(
            VectorDatabaseManager
        )

        manager.document_loader = Mock()
        manager.document_loader.load_single_file.side_effect = batches

        manager.text_splitter = StructuredDocumentSplitter(120, 0)
        manager.add_documents_to_db = Mock()

        return manager

    def test_repeated_upload_has_stable_source_label(self):
        paths = [
            "uploads/upload_first/document.txt",
            "uploads/upload_second/document.txt",
        ]
        manager = self.manager_for([
            [self.document(paths[0])],
            [self.document(paths[1])],
        ])

        for path in paths:
            manager.process_file(
                path,
                "demo",
                file_name="银行制度.txt",
            )

        stored = [
            call.args[0][0]
            for call in manager.add_documents_to_db.call_args_list
        ]

        self.assertEqual(
            [chunk.metadata["source"] for chunk in stored],
            ["银行制度.txt", "银行制度.txt"],
        )
        self.assertEqual(
            [chunk.metadata["file_name"] for chunk in stored],
            ["银行制度.txt", "银行制度.txt"],
        )
        self.assertTrue(all(
            chunk.metadata["document_id"] == "same-content-hash"
            for chunk in stored
        ))

    def test_local_path_keeps_original_source(self):
        path = "D:/documents/bank.txt"
        manager = self.manager_for([
            [self.document(path)]
        ])

        manager.process_file(path, "demo")

        chunks = manager.add_documents_to_db.call_args.args[0]
        self.assertEqual(chunks[0].metadata["source"], path)

    def test_pdf_text_and_table_share_original_label(self):
        path = "uploads/upload_first/document.pdf"

        documents = [
            self.document(
                path,
                "# 转账规则\n办理前核对材料。",
                file_type="pdf",
                page_number=1,
            ),
            self.document(
                path,
                "表格暂存内容",
                file_type="pdf",
                page_number=2,
                content_type="table",
                table_data={
                    "headers": ["编号", "材料"],
                    "rows": [["001", "身份证件"]],
                },
            ),
        ]
        manager = self.manager_for([documents])

        manager.process_file(
            path,
            "demo",
            file_name="银行制度.pdf",
        )

        chunks = manager.add_documents_to_db.call_args.args[0]

        self.assertEqual(len(chunks), 2)
        self.assertEqual(
            {chunk.metadata["content_type"] for chunk in chunks},
            {"text", "table"},
        )
        self.assertTrue(all(
            chunk.metadata["source"] == "银行制度.pdf"
            and chunk.metadata["file_name"] == "银行制度.pdf"
            and chunk.metadata["document_id"] == "same-content-hash"
            for chunk in chunks
        ))