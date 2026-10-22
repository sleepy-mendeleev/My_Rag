import unittest
from copy import deepcopy

from langchain_core.documents import Document

from backend.app.ingestion_identity import build_ingestion_key


class IngestionIdentityTests(unittest.TestCase):
    def setUp(self):
        self.settings = {
            "chunk_size": 500,
            "chunk_overlap": 50,
            "embedding_model": "dashscope:text-embedding-v1",
            "semantic_threshold": 0.45,
        }

    @staticmethod
    def chunk(**metadata):
        fields = {
            "source": "银行制度.txt",
            "file_name": "银行制度.txt",
            "document_id": "doc-1",
            "section_id": "section-1",
            "chunk_id": "chunk-1",
            "chunk_index": 0,
            "parser_version": "structure-v1",
            "splitter_version": "semantic-v1",
            "content_type": "text",
        }
        fields.update(metadata)

        return Document(
            page_content="材料齐全即可办理。",
            metadata=fields,
        )

    def test_same_input_is_stable_and_unchanged(self):
        chunk = self.chunk()
        before = deepcopy(chunk.metadata)

        first = build_ingestion_key(chunk, **self.settings)
        second = build_ingestion_key(chunk, **self.settings)

        self.assertEqual(first, second)
        self.assertEqual(chunk.metadata, before)
        self.assertEqual(chunk.page_content, "材料齐全即可办理。")

    def test_different_provenance_or_version_has_different_key(self):
        original = build_ingestion_key(
            self.chunk(), **self.settings
        )

        changes = (
            ("source", "另一份制度.txt"),
            ("document_id", "doc-2"),
            ("section_id", "section-2"),
            ("chunk_index", 1),
            ("parser_version", "structure-v2"),
            ("splitter_version", "structure-v2"),
        )

        for field, value in changes:
            with self.subTest(field=field):
                changed = self.chunk(**{field: value})
                key = build_ingestion_key(changed, **self.settings)
                self.assertNotEqual(original, key)

    def test_changed_content_has_different_key(self):
        chunk = self.chunk()
        original = build_ingestion_key(chunk, **self.settings)

        chunk.page_content = "材料不齐不得办理。"

        changed = build_ingestion_key(chunk, **self.settings)
        self.assertNotEqual(original, changed)

    def test_changed_processing_settings_have_different_key(self):
        original = build_ingestion_key(
            self.chunk(), **self.settings
        )

        changes = (
            ("chunk_size", 600),
            ("chunk_overlap", 0),
            ("embedding_model", "dashscope:text-embedding-v2"),
            ("semantic_threshold", 0.8),
            ("semantic_threshold", None),
        )

        for field, value in changes:
            with self.subTest(field=field, value=value):
                settings = dict(self.settings)
                settings[field] = value

                changed = build_ingestion_key(
                    self.chunk(), **settings
                )
                self.assertNotEqual(original, changed)

    def test_incomplete_identity_or_nonfinite_setting_raises(self):
        chunk = self.chunk()
        chunk.metadata.pop("source")

        with self.assertRaisesRegex(ValueError, "source"):
            build_ingestion_key(chunk, **self.settings)

        settings = dict(self.settings)
        settings["semantic_threshold"] = float("nan")

        with self.assertRaises(ValueError):
            build_ingestion_key(self.chunk(), **settings)