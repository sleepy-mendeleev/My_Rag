import unittest
from pathlib import Path

from backend.app.pdf_layout import order_text_blocks
from backend.app.pdf_parser import extract_pdf_pages


def block(text, x, y, width=180):
    return {"text": text, "bbox": [x, y, x + width, y + 30]}


class PDFLayoutTests(unittest.TestCase):
    def test_real_pdf_with_middle_title(self):
        root = Path(__file__).resolve().parents[2]
        pages = extract_pdf_pages(
            str(root / "data/samples/bank_pdf_two_columns_demo.pdf")
        )
        texts = [item["text"] for item in pages[0]["blocks"]]
        labels = [
            text.split("：")[0]
            for text in texts
            if text.startswith(("左栏", "右栏"))
        ]

        self.assertEqual(labels, [
            "左栏一", "左栏二", "右栏一", "右栏二",
            "左栏三", "左栏四", "右栏三", "右栏四",
        ])

        joined = "\n".join(texts)
        self.assertLess(joined.index("右栏二"), joined.index("第二章"))
        self.assertLess(joined.index("第二章"), joined.index("左栏三"))
        self.assertTrue(texts[-1].startswith("本样例仅用于开发测试"))

    def test_single_column_indentation_keeps_order(self):
        items = [
            block("A", 50, 50), block("B", 330, 100),
            block("C", 50, 150), block("D", 330, 200),
        ]
        result = order_text_blocks(items, 600)
        self.assertEqual(result, items)
        self.assertEqual(sorted(map(id, result)), sorted(map(id, items)))

    def test_three_columns_fall_back(self):
        items = [
            block(str(row) + str(col), x, y, width=120)
            for row, y in enumerate((50, 100))
            for col, x in enumerate((30, 230, 430))
        ]
        result = order_text_blocks(items, 600)
        self.assertEqual(result, items)
        self.assertEqual(sorted(map(id, result)), sorted(map(id, items)))


if __name__ == "__main__":
    unittest.main()