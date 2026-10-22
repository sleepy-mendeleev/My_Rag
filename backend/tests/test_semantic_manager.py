import os
import unittest
from unittest.mock import Mock, patch

from langchain_core.documents import Document

from backend.app.vector_db_manager import VectorDatabaseManager


TEXT = (
    "核对收款账号。"
    "保存转账回单。"
    "申请贷款需要收入证明。"
)


class SemanticManagerTests(unittest.TestCase):
    @staticmethod
    def create_manager(settings):
        embeddings = Mock()
        embeddings.embed_documents.return_value = [
            [1.0, 0.0],
            [1.0, 0.0],
            [0.0, 1.0],
        ]

        def fake_init_embeddings(manager):
            manager.embeddings = embeddings

        with (
            patch.dict(os.environ, settings, clear=True),
            patch.object(
                VectorDatabaseManager,
                "_init_embeddings",
                fake_init_embeddings,
            ),
            patch.object(
                VectorDatabaseManager,
                "_connect_to_milvus",
            ),
        ):
            manager = VectorDatabaseManager(
                chunk_size=120,
                chunk_overlap=0,
            )

        return manager, embeddings

    @staticmethod
    def document():
        return Document(
            page_content=TEXT,
            metadata={
                "source": "demo.txt",
                "document_id": "demo",
                "content_type": "text",
            },
        )

    def test_enabled_uses_existing_model_and_semantic_groups(self):
        manager, embeddings = self.create_manager({
            "SEMANTIC_SPLIT_ENABLED": "true",
            "SEMANTIC_SIMILARITY_THRESHOLD": "0.45",
        })

        chunks = manager.split_documents([self.document()])

        self.assertIs(
            manager.text_splitter.embeddings,
            embeddings,
        )
        self.assertEqual(
            [chunk.page_content for chunk in chunks],
            [
                "核对收款账号。保存转账回单。",
                "申请贷款需要收入证明。",
            ],
        )
        self.assertTrue(all(
            chunk.metadata["splitter_version"] == "semantic-v1"
            for chunk in chunks
        ))
        embeddings.embed_documents.assert_called_once()

    def test_default_and_disabled_skip_semantic_embedding(self):
        settings_list = [
            {},
            {
                "SEMANTIC_SPLIT_ENABLED": "false",
                "SEMANTIC_SIMILARITY_THRESHOLD": "bad",
            },
        ]

        for settings in settings_list:
            with self.subTest(settings=settings):
                manager, embeddings = self.create_manager(settings)

                chunks = manager.split_documents([self.document()])

                self.assertIsNone(
                    manager.text_splitter.embeddings
                )
                self.assertEqual(
                    [chunk.page_content for chunk in chunks],
                    [TEXT],
                )
                self.assertEqual(
                    chunks[0].metadata["splitter_version"],
                    "structure-v2",
                )
                embeddings.embed_documents.assert_not_called()

    def test_invalid_configuration_raises(self):
        settings_list = [
            {"SEMANTIC_SPLIT_ENABLED": "tru"},
            {"SEMANTIC_SPLIT_ENABLED": "true"},
        ]

        for threshold in ("bad", "nan", "inf", "1.1", "-1.1"):
            settings_list.append({
                "SEMANTIC_SPLIT_ENABLED": "true",
                "SEMANTIC_SIMILARITY_THRESHOLD": threshold,
            })

        for settings in settings_list:
            with self.subTest(settings=settings):
                with self.assertRaises(ValueError):
                    self.create_manager(settings)