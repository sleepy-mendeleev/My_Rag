import unittest

from backend.app.text_cleaner import clean_text


class TextCleanerTests(unittest.TestCase):
    def test_newlines_and_extra_blank_lines(self):
        source = "\ufeff第一章 规则\r\n\r\n\r\n办理要求。\r下一行。"

        self.assertEqual(
            clean_text(source),
            "第一章 规则\n\n办理要求。\n下一行。",
        )

    def test_business_content_is_preserved(self):
        text = (
            "这是客户的材料，原则上不得超过人民币50万元；"
            "产品编号001；日期2026-10-18；"
            "公式x² ≤ 10；单位㎏；编号①。"
        )

        self.assertEqual(clean_text(text), text)

    def test_markdown_structure_is_preserved(self):
        text = (
            "# 标题\n\n"
            "- 提交客户的材料。\n\n"
            "| 编号 | 金额 |\n"
            "| --- | --- |\n"
            "| 001 | 50万元 |\n\n"
            "说明  \n下一行"
        )

        self.assertEqual(clean_text(text), text)

    def test_code_blocks_are_preserved(self):
        examples = [
            "```python\nif True:\n    value = 'A  B'\n\n\nprint(value)\n```",
            "````text\nA\n\n\n```\n\n\nB\n````",
            "~~~text\nA\n\n\nB\n~~~",
            "    value = 'A  B'\n\n\n    print(value)",
        ]

        for text in examples:
            with self.subTest(text=text):
                self.assertEqual(clean_text(text), text)

    def test_cleaning_is_idempotent(self):
        source = "\ufeff正文\r\n\r\n\r\n```text\r\nA\r\n\r\n\r\nB\r\n```"
        once = clean_text(source)

        self.assertEqual(clean_text(once), once)

    def test_plain_control_characters_keep_boundaries(self):
        examples = [
            ("前页正文。\f后页正文。", "前页正文。\n\n后页正文。"),
            ("第一行\v第二行", "第一行\n第二行"),
            ("AB\x00CD", "AB CD"),
            ("001\x00002", "001 002"),
            ("A\tB", "A\tB"),
        ]

        for source, expected in examples:
            with self.subTest(source=source):
                self.assertEqual(clean_text(source), expected)

    def test_control_characters_in_code_are_preserved(self):
        examples = [
            "```text\nA\x00B\fC\vD\n```",
            "    A\x00B\fC\vD",
            "说明：`A\x00B\fC`",
        ]

        for text in examples:
            with self.subTest(text=text):
                self.assertEqual(clean_text(text), text)

    def test_page_break_before_code_fence(self):
        source = "正文\f~~~text\nA\n\n\nB\n~~~"
        expected = "正文\n\n~~~text\nA\n\n\nB\n~~~"

        cleaned = clean_text(source)

        self.assertEqual(cleaned, expected)
        self.assertEqual(clean_text(cleaned), cleaned)

    def test_only_allowed_spaces_are_normalized(self):
        source = (
            "产品编号：００１\u3000金额：５０万元\u00a0"
            "原则上不得超额；①，x²，㎏。"
        )
        expected = (
            "产品编号：００１ 金额：５０万元 "
            "原则上不得超额；①，x²，㎏。"
        )

        cleaned = clean_text(source)

        self.assertEqual(cleaned, expected)
        self.assertEqual(clean_text(cleaned), cleaned)

    def test_line_edges_are_preserved(self):
        examples = [
            (
                "\u3000正文\u3000内容\u00a0\u00a0",
                "\u3000正文 内容\u00a0\u00a0",
            ),
            (
                "说明\u3000内容  \n下一行",
                "说明 内容  \n下一行",
            ),
        ]

        for source, expected in examples:
            with self.subTest(source=source):
                self.assertEqual(clean_text(source), expected)
                self.assertEqual(clean_text(expected), expected)

    def test_special_spaces_in_code_are_preserved(self):
        examples = [
            "```text\nＡ\u3000Ｂ\u00a0Ｃ\n```",
            "    Ａ\u3000Ｂ\u00a0Ｃ",
            "说明：`Ａ\u3000Ｂ\u00a0Ｃ`",
        ]

        for text in examples:
            with self.subTest(text=text):
                self.assertEqual(clean_text(text), text)


if __name__ == "__main__":
    unittest.main()