"""Offline acceptance checks for native PDF table integration; no database calls."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pymupdf

from backend.app.document_loader import DocumentLoader
from backend.app.document_splitter import StructuredDocumentSplitter
from backend.app.pdf_parser import extract_pdf_pages
from backend.app.pdf_tables import extract_pdf_tables
from backend.app.table_splitter import TableSplitter


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_PDF = PROJECT_ROOT / "data" / "samples" / "bank_pdf_table_demo.pdf"
SAMPLE_HEADING = "\u7b2c\u4e00\u7ae0 \u5ba2\u6237\u4e1a\u52a1\u529e\u7406"


def draw_table(page, top, code):
    """Draw one ordinary two-column table with a header and one data row."""
    left, middle, right = 50, 210, 460
    for x in (left, middle, right):
        page.draw_line((x, top), (x, top + 60))
    for y in (top, top + 30, top + 60):
        page.draw_line((left, y), (right, y))
    page.insert_text((left + 6, top + 20), "Code", fontsize=11)
    page.insert_text((middle + 6, top + 20), "Product", fontsize=11)
    page.insert_text((left + 6, top + 50), code, fontsize=11)
    page.insert_text((middle + 6, top + 50), "Loan " + code, fontsize=11)


def save_table_pdf(path, tables_per_page):
    """Generate real temporary PDFs instead of mocking geometric extraction."""
    with pymupdf.open() as pdf:
        for page_index, codes in enumerate(tables_per_page, 1):
            page = pdf.new_page(width=612, height=792)
            page.insert_text((50, 100), "# Page " + str(page_index), fontsize=12)
            for table_index, code in enumerate(codes):
                draw_table(page, 160 + table_index * 200, code)
            page.insert_text((50, 650), "End of page " + str(page_index), fontsize=11)
        pdf.save(path)


class PdfTableTests(unittest.TestCase):
    def test_page_table_preview_interface_survives_block_integration(self):
        pages = extract_pdf_pages(str(SAMPLE_PDF))
        self.assertEqual(len(pages), 1)
        self.assertIn("tables", pages[0])
        self.assertEqual(pages[0]["tables"], extract_pdf_tables(str(SAMPLE_PDF)))
        blocks = [block for block in pages[0]["blocks"] if "table_data" in block]
        self.assertEqual(len(blocks), 1)
        raw_table = pages[0]["tables"][0]
        self.assertEqual(blocks[0]["bbox"], raw_table["bbox"])
        self.assertEqual(blocks[0]["table_number"], raw_table["table_number"])
        self.assertEqual(blocks[0]["table_data"], {
            "headers": raw_table["headers"], "rows": raw_table["rows"]
        })

    def test_table_only_page_keeps_native_text_and_is_not_empty_after_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "table_only.pdf"
            with pymupdf.open() as pdf:
                page = pdf.new_page(width=612, height=792)
                draw_table(page, 160, "001")
                pdf.save(path)

            pages = extract_pdf_pages(str(path))
            self.assertEqual(len(pages), 1)
            self.assertTrue(pages[0]["has_native_text"])
            self.assertEqual(len(pages[0]["tables"]), 1)
            self.assertEqual(len(pages[0]["blocks"]), 1)
            self.assertEqual(pages[0]["blocks"][0]["table_data"]["rows"], [["001", "Loan 001"]])

            documents = DocumentLoader().load_single_file(str(path))
            self.assertEqual(len(documents), 1)
            self.assertEqual(documents[0].metadata["content_type"], "table")
            self.assertEqual(documents[0].metadata["page_number"], 1)
            self.assertIn("001", documents[0].page_content)

    def test_shared_block_preserves_both_before_and_after_table_prose_in_order(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "both_table_edges.pdf"
            with pymupdf.open() as pdf:
                page = pdf.new_page(width=612, height=792)
                page.insert_text(
                    (55, 110), "OUTSIDE BEFORE\nCode\n001\nOUTSIDE AFTER",
                    fontsize=10, lineheight=1.5,
                )
                page.insert_text((245, 125), "Product", fontsize=10)
                page.insert_text((245, 140), "Inside", fontsize=10)
                for x in (50, 240, 450):
                    page.draw_line((x, 118), (x, 148))
                for y in (118, 133, 148):
                    page.draw_line((50, y), (450, y))
                pdf.save(path)

            with pymupdf.open(path) as pdf:
                native_blocks = [block[4] for block in pdf[0].get_text("blocks") if block[6] == 0]
            self.assertTrue(
                any(all(marker in text for marker in ("OUTSIDE BEFORE", "001", "OUTSIDE AFTER"))
                    for text in native_blocks),
                "The fixture must share one native block across both table boundaries.",
            )

            documents = DocumentLoader().load_single_file(str(path))
            self.assertEqual(
                [doc.metadata.get("content_type") for doc in documents],
                ["text", "table", "text"],
            )
            self.assertIn("OUTSIDE BEFORE", documents[0].page_content)
            self.assertNotIn("OUTSIDE AFTER", documents[0].page_content)
            self.assertEqual(documents[1].metadata["table_data"]["rows"], [["001", "Inside"]])
            self.assertIn("OUTSIDE AFTER", documents[2].page_content)
            self.assertNotIn("001", documents[0].page_content + documents[2].page_content)
            self.assertEqual(sum(doc.page_content.count("OUTSIDE BEFORE") for doc in documents), 1)
            self.assertEqual(sum(doc.page_content.count("OUTSIDE AFTER") for doc in documents), 1)

    def test_sample_keeps_text_table_text_and_inherits_heading(self):
        documents = DocumentLoader().load_single_file(str(SAMPLE_PDF))
        self.assertEqual(
            [doc.metadata.get("content_type") for doc in documents],
            ["text", "table", "text"],
        )
        table = documents[1]
        self.assertEqual(table.metadata["page_number"], 1)
        self.assertEqual(table.metadata["table_number"], 1)
        self.assertEqual(len(table.metadata["table_bbox"]), 4)
        self.assertEqual(table.metadata["source"], str(SAMPLE_PDF))
        self.assertIn("001", table.page_content)
        self.assertNotIn("001", documents[0].page_content)
        self.assertNotIn("001", documents[2].page_content)
        self.assertEqual(sum(doc.page_content.count("001") for doc in documents), 1)

        chunks = StructuredDocumentSplitter().split_documents(documents)
        table_chunks = [doc for doc in chunks if doc.metadata.get("content_type") == "table"]
        self.assertTrue(table_chunks)
        self.assertEqual(sum(doc.page_content.count("001") for doc in table_chunks), 1)
        for chunk in table_chunks:
            self.assertEqual(chunk.metadata["heading_path"], [SAMPLE_HEADING])
            self.assertEqual(chunk.metadata["page_number"], 1)
            self.assertEqual(chunk.metadata["table_number"], 1)
            self.assertEqual(chunk.metadata["table_bbox"], table.metadata["table_bbox"])
            self.assertEqual(chunk.metadata["splitter_version"], "table-v1")

    def test_raw_sample_preserves_leading_zero_empty_cell_and_cell_newline(self):
        tables = extract_pdf_tables(str(SAMPLE_PDF))
        self.assertEqual(len(tables), 1)
        table = tables[0]
        self.assertFalse(table["needs_review"])
        self.assertEqual(table["page_number"], 1)
        self.assertEqual(table["rows"][0][0], "001")
        self.assertIsInstance(table["rows"][0][0], str)
        self.assertEqual(table["rows"][2][2], "")
        self.assertIn("\n", table["rows"][0][3])
        self.assertTrue(all(len(row) == len(table["headers"]) for row in table["rows"]))

    def test_shared_native_block_does_not_swallow_text_outside_table(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "shared_block.pdf"
            with pymupdf.open() as pdf:
                page = pdf.new_page(width=612, height=792)
                # One text insertion deliberately spans the table's upper boundary.
                page.insert_text(
                    (55, 110), "OUTSIDE PROSE\nCode\n001", fontsize=10, lineheight=1.5
                )
                page.insert_text((245, 125), "Product", fontsize=10)
                page.insert_text((245, 140), "Inside", fontsize=10)
                for x in (50, 240, 450):
                    page.draw_line((x, 118), (x, 148))
                for y in (118, 133, 148):
                    page.draw_line((50, y), (450, y))
                pdf.save(path)

            with pymupdf.open(path) as pdf:
                native_blocks = [block[4] for block in pdf[0].get_text("blocks") if block[6] == 0]
            self.assertTrue(
                any("OUTSIDE PROSE" in text and "001" in text for text in native_blocks),
                "The fixture must really contain prose and a table cell in one native block.",
            )
            documents = DocumentLoader().load_single_file(str(path))
            prose = "\n".join(
                doc.page_content for doc in documents if doc.metadata.get("content_type") == "text"
            )
            tables = [doc for doc in documents if doc.metadata.get("content_type") == "table"]
            self.assertIn("OUTSIDE PROSE", prose)
            self.assertNotIn("001", prose)
            self.assertEqual(len(tables), 1)
            self.assertEqual(tables[0].metadata["table_data"]["rows"], [["001", "Inside"]])

    def test_same_page_tables_stay_separate_and_ordered(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "two_tables.pdf"
            save_table_pdf(path, [["001", "002"]])
            documents = DocumentLoader().load_single_file(str(path))
            tables = [doc for doc in documents if doc.metadata.get("content_type") == "table"]
            self.assertEqual([doc.metadata["table_number"] for doc in tables], [1, 2])
            self.assertEqual([doc.metadata["page_number"] for doc in tables], [1, 1])
            self.assertEqual(
                [doc.metadata["table_data"]["rows"][0][0] for doc in tables], ["001", "002"]
            )
            self.assertLess(tables[0].metadata["table_bbox"][1], tables[1].metadata["table_bbox"][1])
            prose = "\n".join(
                doc.page_content for doc in documents if doc.metadata.get("content_type") == "text"
            )
            self.assertIn("End of page 1", prose)
            self.assertNotIn("001", prose)
            self.assertNotIn("002", prose)

    def test_tables_on_different_pages_keep_page_and_heading(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "two_pages.pdf"
            save_table_pdf(path, [["001"], ["002"]])
            documents = DocumentLoader().load_single_file(str(path))
            chunks = StructuredDocumentSplitter().split_documents(documents)
            tables = [doc for doc in chunks if doc.metadata.get("content_type") == "table"]
            self.assertEqual([doc.metadata["page_number"] for doc in tables], [1, 2])
            self.assertEqual([doc.metadata["heading_path"] for doc in tables], [["Page 1"], ["Page 2"]])
            self.assertEqual(len({doc.metadata["table_id"] for doc in tables}), 2)
            self.assertEqual(len({doc.metadata["document_id"] for doc in tables}), 1)
            self.assertIn("001", tables[0].page_content)
            self.assertNotIn("002", tables[0].page_content)
            self.assertIn("002", tables[1].page_content)

    def test_table_needing_review_is_rejected_before_silent_ingestion(self):
        damaged = [{
            "source": str(SAMPLE_PDF),
            "page_number": 1,
            "table_number": 1,
            "bbox": [50, 180, 545, 388],
            "headers": ["Code", "Product"],
            "rows": [["001", None]],
            "needs_review": True,
        }]
        with patch("backend.app.pdf_parser.extract_pdf_tables", return_value=damaged):
            with self.assertRaises(ValueError):
                DocumentLoader().load_single_file(str(SAMPLE_PDF))

    def test_rotated_page_with_table_is_explicitly_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rotated.pdf"
            with pymupdf.open(SAMPLE_PDF) as pdf:
                pdf[0].set_rotation(90)
                pdf.save(path)
            with self.assertRaisesRegex(ValueError, r"(?i)rotat|\u65cb\u8f6c"):
                DocumentLoader().load_single_file(str(path))

    def test_small_table_budget_repeats_header_and_covers_complete_rows(self):
        headers = ["Code", "Description"]
        rows = [[f"{number:03d}", f"Item {number} requires documents and supporting details"]
                for number in range(1, 9)]
        metadata = {"source": "table.pdf", "page_number": 1, "heading_path": [SAMPLE_HEADING]}
        chunks = TableSplitter(max_chars=125).split(headers, rows, metadata=metadata)
        self.assertGreater(len(chunks), 1)
        covered_rows = []
        for chunk in chunks:
            self.assertTrue(chunk.page_content.startswith("| Code | Description |\n| --- | --- |"))
            self.assertEqual(chunk.page_content.count("| Code | Description |"), 1)
            self.assertEqual(chunk.metadata["page_number"], 1)
            self.assertEqual(chunk.metadata["heading_path"], [SAMPLE_HEADING])
            start, end = chunk.metadata["row_start"], chunk.metadata["row_end"]
            covered_rows.extend(range(start, end + 1))
            self.assertEqual(len(chunk.page_content.splitlines()) - 2, end - start + 1)
            for row_number in range(start, end + 1):
                code, description = rows[row_number - 1]
                self.assertIn(f"| {code} | {description} |", chunk.page_content)
        self.assertEqual(covered_rows, list(range(1, len(rows) + 1)))
        all_content = "\n".join(chunk.page_content for chunk in chunks)
        for number in range(1, 9):
            self.assertEqual(all_content.count(f"| {number:03d} |"), 1)


if __name__ == "__main__":
    unittest.main()
