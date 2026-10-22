import unittest
from unittest.mock import Mock

from langchain_core.documents import Document

from backend.app.document_splitter import StructuredDocumentSplitter


class SemanticDocumentSplitterTests(unittest.TestCase):
    @staticmethod
    def document(text, **metadata):
        return Document(
            page_content=text,
            metadata={
                "source": "demo.txt",
                "document_id": "demo",
                "content_type": "text",
                **metadata,
            },
        )

    def test_semantic_groups_respect_section_boundaries(self):
        embeddings = Mock()
        embeddings.embed_documents.return_value = [
            [1.0, 0.0],
            [0.0, 1.0],
        ]
        splitter = StructuredDocumentSplitter(
            120, 0,
            embeddings=embeddings,
            semantic_threshold=0.45,
        )
        source = self.document(
            "# 转账\n核对账号。\n\n保存回单。\n"
            "# 贷款\n提交收入证明。核对还款计划。"
        )

        chunks = splitter.split_documents([source])

        self.assertEqual(len(chunks), 4)
        self.assertEqual(embeddings.embed_documents.call_count, 2)
        self.assertEqual(
            [chunk.metadata["heading_path"] for chunk in chunks],
            [["转账"], ["转账"], ["贷款"], ["贷款"]],
        )
        self.assertIn("\n\n", chunks[0].page_content)
        self.assertTrue(all(
            chunk.metadata["splitter_version"] == "semantic-v1"
            for chunk in chunks
        ))

    def test_short_article_and_table_skip_embedding(self):
        embeddings = Mock()
        splitter = StructuredDocumentSplitter(
            80, 10,
            embeddings=embeddings,
            semantic_threshold=0.45,
        )

        article = self.document(
            "# 办理\n第一条\n材料齐全。核对身份。"
        )
        chunks = splitter.split_documents([article])

        self.assertEqual(len(chunks), 1)
        self.assertEqual(
            chunks[0].metadata["splitter_version"], "structure-v2"
        )

        table = self.document(
            "临时表格文本",
            file_type="csv",
            content_type="table",
            table_data={
                "headers": ["编号", "材料"],
                "rows": [["001", "材料" * 60]],
            },
        )
        chunks = splitter.split_documents([table])

        embeddings.embed_documents.assert_not_called()
        self.assertEqual(
            chunks[0].metadata["splitter_version"], "table-v1"
        )
        self.assertTrue(chunks[0].metadata["oversized"])
        self.assertEqual(chunks[0].metadata["row_start"], 1)
        self.assertEqual(chunks[0].metadata["row_end"], 1)

    def test_prefix_budget_and_model_failure_fallback(self):
        title = "业务规则" * 9
        source = self.document(
            "# " + title + "\n" + "核对材料。" * 35 + "保存回单。"
        )
        prefix = f"【标题路径】{title}\n"

        for failure in (False, True):
            with self.subTest(failure=failure):
                embeddings = Mock()

                if failure:
                    embeddings.embed_documents.side_effect = RuntimeError(
                        "模拟服务不可用"
                    )
                else:
                    embeddings.embed_documents.side_effect = (
                        lambda units: [[1.0, 0.0] for _ in units]
                    )

                splitter = StructuredDocumentSplitter(
                    90, 50,
                    embeddings=embeddings,
                    semantic_threshold=0.45,
                )

                if failure:
                    with self.assertLogs(
                        "backend.app.document_splitter",
                        level="WARNING",
                    ):
                        chunks = splitter.split_documents([source])
                else:
                    chunks = splitter.split_documents([source])

                expected_version = (
                    "structure-v2" if failure else "semantic-v1"
                )
                self.assertGreater(len(chunks), 1)
                self.assertTrue(all(
                    len(chunk.page_content) <= 90 for chunk in chunks
                ))
                self.assertTrue(all(
                    chunk.page_content.startswith(prefix)
                    for chunk in chunks
                ))
                self.assertTrue(all(
                    chunk.metadata["splitter_version"] == expected_version
                    for chunk in chunks
                ))
                embeddings.embed_documents.assert_called_once()

    def test_prefix_exhaustion_and_one_character_budget(self):
        embeddings = Mock()
        splitter = StructuredDocumentSplitter(
            20, 0,
            embeddings=embeddings,
            semantic_threshold=0.45,
        )
        source = self.document(
            "# " + "长标题" * 10 + "\n正文。"
        )

        with self.assertRaisesRegex(ValueError, "标题前缀"):
            splitter.split_documents([source])

        embeddings.embed_documents.assert_not_called()

        tiny_splitter = StructuredDocumentSplitter(1, 0)
        chunks = tiny_splitter.split_documents([
            self.document("甲乙丙")
        ])

        self.assertEqual(
            [chunk.page_content for chunk in chunks],
            ["甲", "乙", "丙"],
        )