"""Offline checks for conservative PDF header/footer filtering."""
import tempfile
import unittest
from pathlib import Path

from backend.app.pdf_margins import filter_repeated_margins
from backend.app.pdf_parser import extract_pdf_pages


def block(text, y, x=50):
    return {"text": text, "bbox": [x, y, x + 200, y + 10]}


def page(number, blocks):
    return {
        "page_number": number, "width": 600, "height": 800,
        "has_native_text": bool(blocks), "blocks": blocks,
    }


def write_header_pdf(path, with_body):
    import pymupdf
    with pymupdf.open() as pdf:
        for index in range(2):
            sheet = pdf.new_page(width=600, height=800)
            sheet.insert_text((50, 28), "Repeated header")
            if with_body and index == 1:
                sheet.insert_text((50, 200), "Actual body.")
        pdf.save(str(path))


class PDFMarginTests(unittest.TestCase):
    def test_real_pdf_footer_removed_without_losing_text(self):
        root = Path(__file__).resolve().parents[2]
        pages = extract_pdf_pages(str(root / "data/samples/bank_pdf_demo.pdf"))
        self.assertEqual([item["page_number"] for item in pages], [1, 2])
        self.assertTrue(all(item["has_native_text"] for item in pages))
        joined = "\n".join(
            item["text"] for sheet in pages for item in sheet["blocks"]
        )
        self.assertNotIn("仅用于开发测试，不代表真实银行制度。", joined)
        self.assertIn("第一章 转账规则", joined)
        self.assertIn("初步审核不等于审批通过。", joined)

    def test_body_titles_notes_and_numbers_are_preserved(self):
        original = [
            page(number, [
                block("重复页眉", 5),
                block("第一章 客户身份核验", 20),
                block("表：收费标准", 35),
                block("V1.2 编号001 2026年", 50),
                block("重复页眉", 200),
                block("注：金额单位为万元。", 750),
                block(f"{number} / 2", 775),
            ])
            for number in (1, 2)
        ]
        result = filter_repeated_margins(original)
        for sheet in result:
            self.assertEqual([item["text"] for item in sheet["blocks"]], [
                "第一章 客户身份核验", "表：收费标准", "V1.2 编号001 2026年",
                "重复页眉", "注：金额单位为万元。",
            ])
        self.assertEqual(len(original[0]["blocks"]), 7)

    def test_single_page_low_frequency_and_unstable_positions_are_kept(self):
        cases = [
            [page(1, [block("页眉", 10)])],
            [
                page(number, [block(text, 10)])
                for number, text in enumerate(
                    ["共同页眉", "共同页眉", "甲", "乙", "丙"], 1
                )
            ],
            [
                page(1, [block("相同页眉", 10, x=50)]),
                page(2, [block("相同页眉", 10, x=200)]),
            ],
        ]
        for pages in cases:
            with self.subTest(pages=len(pages)):
                self.assertEqual(filter_repeated_margins(pages), pages)

    def test_cleaned_empty_page_keeps_native_flag_and_page_number(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "header_and_body.pdf"
            write_header_pdf(path, with_body=True)
            pages = extract_pdf_pages(str(path))
        self.assertEqual(pages[0]["page_number"], 1)
        self.assertTrue(pages[0]["has_native_text"])
        self.assertEqual(pages[0]["blocks"], [])
        self.assertIn("Actual body.", pages[1]["blocks"][0]["text"])

    def test_all_headers_raise_cleanup_error_instead_of_ocr_error(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "headers_only.pdf"
            write_header_pdf(path, with_body=False)
            with self.assertRaisesRegex(ValueError, "清理后没有有效正文"):
                extract_pdf_pages(str(path))


if __name__ == "__main__":
    unittest.main()

