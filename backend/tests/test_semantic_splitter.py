import unittest

from unittest.mock import Mock
from backend.app.semantic_splitter import (
    group_semantic_units,
    semantic_split_text,
    split_semantic_units,
)


class SemanticUnitTests(unittest.TestCase):
    def test_sentences_keep_numbers_and_quotes(self):
        text = (
            "编号001，金额为3.14万元，原则上不得超额。"
            "“请核对材料！”"
            "下一项？"
        )

        self.assertEqual(
            split_semantic_units(text),
            [
                "编号001，金额为3.14万元，原则上不得超额。",
                "“请核对材料！”",
                "下一项？",
            ],
        )

    def test_whitespace_and_paragraphs_are_preserved(self):
        text = "\n\n第一段没有句末标点\r\n \r\n第二段。\n\n第三段。  "
        units = split_semantic_units(text)

        self.assertGreater(len(units), 1)
        self.assertEqual("".join(units), text)
        self.assertTrue(all(unit.strip() for unit in units))

    def test_marked_structures_stay_together(self):
        cases = [
            "```python\nprint('第一句。第二句。')\n```",
            "    print('第一句。第二句。')",
            "- 提交身份证。\n- 提交收入证明。",
            "1、提交身份证。\n2、提交收入证明。",
            "公式为 $x+1$。请核对。",
            r"\[a+b。\]",
        ]

        for text in cases:
            with self.subTest(text=text):
                self.assertEqual(split_semantic_units(text), [text])

    def test_empty_and_whitespace_input(self):
        self.assertEqual(split_semantic_units(""), [])
        self.assertEqual(split_semantic_units(" \n"), [" \n"])

class SemanticGroupingTests(unittest.TestCase):
    def test_topic_change_and_original_text(self):
        units = [
            "核对收款账号。",
            "\n转账后保存回单。\n\n",
            "贷款需提供收入证明。  ",
        ]
        vectors = [
            [1.0, 0.0],
            [0.9, 0.1],
            [0.0, 1.0],
        ]

        groups = group_semantic_units(units, vectors, 0.8)

        self.assertEqual(
            groups,
            [
                "核对收款账号。\n转账后保存回单。\n\n",
                "贷款需提供收入证明。  ",
            ],
        )
        self.assertEqual("".join(groups), "".join(units))

    def test_equal_threshold_keeps_same_group(self):
        groups = group_semantic_units(
            ["第一句。", "第二句。"],
            [[1.0, 0.0], [0.0, 1.0]],
            0.0,
        )

        self.assertEqual(groups, ["第一句。第二句。"])

    def test_empty_and_single_unit(self):
        self.assertEqual(group_semantic_units([], [], 0.8), [])
        self.assertEqual(
            group_semantic_units(
                ["材料不完整时暂停办理。"],
                [[1.0, 0.0]],
                0.8,
            ),
            ["材料不完整时暂停办理。"],
        )

    def test_invalid_inputs_raise_errors(self):
        cases = [
            (["甲"], [], 0.8),
            ([], [[1.0, 0.0]], 0.8),
            (["甲"], [[0.0, 0.0]], 0.8),
            (["甲"], [[1.0, 0.0]], float("nan")),
            (["甲"], [[1.0, 0.0]], 1.1),
            (["甲", "乙"], [[1.0, 0.0], [1.0]], 0.8),
        ]

        for units, vectors, threshold in cases:
            with self.subTest(
                units=units,
                vectors=vectors,
                threshold=threshold,
            ):
                with self.assertRaises(ValueError):
                    group_semantic_units(units, vectors, threshold)

class SemanticEntryTests(unittest.TestCase):
    def test_embed_once_and_preserve_text(self):
        text = "核对收款账号。保存转账回单。申请贷款需要收入证明。"
        embeddings = Mock()
        embeddings.embed_documents.return_value = [
            [1.0, 0.0],
            [0.9, 0.1],
            [0.0, 1.0],
        ]

        groups = semantic_split_text(text, embeddings, 0.45)

        self.assertEqual(
            groups,
            [
                "核对收款账号。保存转账回单。",
                "申请贷款需要收入证明。",
            ],
        )
        self.assertEqual("".join(groups), text)
        embeddings.embed_documents.assert_called_once_with(
            split_semantic_units(text)
        )

    def test_atomic_or_empty_text_skips_embedding(self):
        cases = [
            "",
            "材料齐全。",
            "- 提交身份证。\n- 提交收入证明。",
        ]

        for text in cases:
            with self.subTest(text=text):
                embeddings = Mock()

                groups = semantic_split_text(text, embeddings, 0.45)

                self.assertEqual(groups, split_semantic_units(text))
                embeddings.embed_documents.assert_not_called()

    def test_model_errors_are_not_hidden(self):
        text = "第一句。第二句。"
        embeddings = Mock()
        embeddings.embed_documents.return_value = [[1.0, 0.0]]

        with self.assertRaisesRegex(ValueError, "数量"):
            semantic_split_text(text, embeddings, 0.45)

        embeddings.embed_documents.side_effect = RuntimeError(
            "模拟模型服务不可用"
        )

        with self.assertRaises(RuntimeError):
            semantic_split_text(text, embeddings, 0.45)

    def test_invalid_threshold_is_checked_before_embedding(self):
        for threshold in (float("nan"), -1.1, 1.1):
            with self.subTest(threshold=threshold):
                embeddings = Mock()

                with self.assertRaises(ValueError):
                    semantic_split_text("", embeddings, threshold)

                embeddings.embed_documents.assert_not_called()