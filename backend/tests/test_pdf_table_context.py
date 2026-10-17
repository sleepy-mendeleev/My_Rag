"""PDF table context association and chunk-budget acceptance checks, offline."""

import copy
import unittest
from pathlib import Path

from langchain_core.documents import Document

from backend.app.document_loader import DocumentLoader
from backend.app.document_splitter import StructuredDocumentSplitter
from backend.app.pdf_parser import extract_pdf_pages
from backend.app.pdf_margins import filter_repeated_margins
from backend.app.pdf_tables import bind_table_context
from backend.app.table_splitter import TableSplitter


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_PDF = PROJECT_ROOT / "data" / "samples" / "bank_pdf_table_demo.pdf"
SAMPLE_TITLE = "\u88681 \u529e\u7406\u6750\u6599\u4e0e\u8981\u6c42\uff08\u6d4b\u8bd5\u7528\uff09"
SAMPLE_NOTE = (
    "\u6ce8\uff1a\u8868\u5185\u91d1\u989d\u5747\u4e3a\u4eba\u6c11\u5e01\uff1b"
    "\u7a7a\u767d\u5355\u5143\u683c\u5e94\u4fdd\u7559\uff0c"
    "\u4e0d\u81ea\u52a8\u63a8\u65ad\u542b\u4e49\u3002"
)
SAMPLE_HEADING = "\u7b2c\u4e00\u7ae0 \u5ba2\u6237\u4e1a\u52a1\u529e\u7406"
NOTE = "\u6ce8\uff1a"


def text_block(text, bbox, group=None):
    result = {"text": text, "bbox": list(bbox)}
    if group is not None:
        result["text_block"] = group
    return result


def table_block(number=1, bbox=(50, 100, 350, 200)):
    code = f"{number:03d}"
    return {
        "bbox": list(bbox),
        "text": "Code\tProduct\n" + code + "\tLoan",
        "content_type": "table",
        "table_number": number,
        "table_data": {"headers": ["Code", "Product"], "rows": [[code, "Loan"]]},
    }


def tables_in(blocks):
    return [block for block in blocks if "table_data" in block]


class PdfTableContextTests(unittest.TestCase):
    def test_note_continuation_is_protected_with_its_original_paragraph(self):
        for with_identity in (True, False):
            with self.subTest(with_identity=with_identity):
                pages = []
                for number in (1, 2):
                    blocks = [
                        text_block(NOTE + "Personal customers only.", [50, 738, 300, 748], group=7),
                        text_block("Do not apply to corporate customers.", [50, 752, 320, 762], group=7),
                        text_block("Repeated footer", [50, 775, 300, 785], group=9),
                    ]
                    if not with_identity:
                        for block in blocks:
                            block.pop("text_block")
                    pages.append({"page_number": number, "width": 600, "height": 800,
                                  "has_native_text": True, "blocks": blocks})
                result = filter_repeated_margins(pages)
                for page in result:
                    texts = [block["text"] for block in page["blocks"]]
                    self.assertIn(NOTE + "Personal customers only.", texts)
                    if with_identity:
                        self.assertIn("Do not apply to corporate customers.", texts)
                    self.assertNotIn("Repeated footer", texts)

    def test_sample_context_reaches_parser_loader_and_every_table_chunk(self):
        pages = extract_pdf_pages(str(SAMPLE_PDF))
        blocks = tables_in(pages[0]["blocks"])
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].get("table_title"), SAMPLE_TITLE)
        self.assertEqual(blocks[0].get("table_note"), SAMPLE_NOTE)

        documents = DocumentLoader().load_single_file(str(SAMPLE_PDF))
        table_documents = [doc for doc in documents if doc.metadata.get("content_type") == "table"]
        self.assertEqual(len(table_documents), 1)
        self.assertEqual(table_documents[0].metadata.get("table_title"), SAMPLE_TITLE)
        self.assertEqual(table_documents[0].metadata.get("table_note"), SAMPLE_NOTE)

        chunks = StructuredDocumentSplitter(chunk_size=220, chunk_overlap=0).split_documents(documents)
        table_chunks = [doc for doc in chunks if doc.metadata.get("content_type") == "table"]
        self.assertGreater(len(table_chunks), 1)
        for chunk in table_chunks:
            self.assertEqual(chunk.metadata.get("table_title"), SAMPLE_TITLE)
            self.assertEqual(chunk.metadata.get("table_note"), SAMPLE_NOTE)
            self.assertEqual(chunk.metadata["heading_path"], [SAMPLE_HEADING])
            self.assertEqual(chunk.metadata["page_number"], 1)
            self.assertIn(SAMPLE_TITLE, chunk.page_content)
            self.assertIn(SAMPLE_NOTE, chunk.page_content)
            self.assertLess(chunk.page_content.index(SAMPLE_TITLE), chunk.page_content.index("|"))
            self.assertGreater(chunk.page_content.index(SAMPLE_NOTE), chunk.page_content.rindex("|"))

    def test_two_tables_bind_their_own_title_and_note_without_leaking(self):
        first_note = NOTE + "Personal customers only."
        second_note = NOTE + "Corporate customers only."
        blocks = [
            text_block("Table 1: Personal loans", [50, 70, 250, 80]),
            table_block(1, [50, 100, 350, 180]),
            text_block(first_note, [50, 188, 290, 198]),
            text_block("Table 2: Corporate loans", [50, 240, 260, 250]),
            table_block(2, [50, 270, 350, 350]),
            text_block(second_note, [50, 358, 290, 368]),
        ]
        tables = tables_in(bind_table_context(blocks))
        self.assertEqual([item.get("table_title", "") for item in tables],
                         ["Table 1: Personal loans", "Table 2: Corporate loans"])
        self.assertEqual([item.get("table_note", "") for item in tables], [first_note, second_note])

    def test_cross_column_ordinary_barrier_and_overlong_gap_do_not_bind(self):
        note = NOTE + "Unrelated conditions."
        cases = {
            "other_column": [
                text_block("Table 1: Other column", [380, 80, 590, 90]),
                table_block(),
                text_block(note, [380, 210, 590, 220]),
            ],
            "ordinary_prose_blocks_both_directions": [
                text_block("Table 1: Distant caption", [50, 60, 270, 70]),
                text_block("Ordinary paragraph before table.", [50, 80, 300, 90]),
                table_block(),
                text_block("Ordinary paragraph after table.", [50, 205, 300, 215]),
                text_block(note, [50, 220, 290, 230]),
            ],
            "first_gap_exceeds_40_points": [
                text_block("Table 1: Too far", [50, 49, 260, 59]),
                table_block(),
                text_block(note, [50, 241, 290, 251]),
            ],
            "less_than_80_percent_inside_table_width": [
                text_block("Table 1: Overwide", [0, 80, 430, 90]),
                table_block(),
                text_block(note, [0, 210, 430, 220]),
            ],
        }
        for name, blocks in cases.items():
            with self.subTest(case=name):
                table = tables_in(bind_table_context(blocks))[0]
                self.assertFalse(table.get("table_title", ""))
                self.assertFalse(table.get("table_note", ""))

    def test_multiline_note_keeps_complete_paragraph_and_original_blocks(self):
        first_line = NOTE + "Personal customers only."
        continuation = "Do not apply these conditions to corporate customers."
        blocks = [
            text_block("Table 1: Loan rules", [50, 70, 250, 80], group=1),
            table_block(),
            text_block(first_line, [50, 215, 300, 225], group=7),
            text_block(continuation, [50, 228, 340, 238], group=7),
            text_block("Ordinary next paragraph.", [50, 250, 300, 260], group=8),
        ]
        original = copy.deepcopy(blocks)
        result = bind_table_context(blocks)
        self.assertEqual(len(result), len(original))
        self.assertEqual(
            [(block["text"], block["bbox"]) for block in result],
            [(block["text"], block["bbox"]) for block in original],
        )
        for index, block in enumerate(original):
            if "table_data" not in block:
                self.assertEqual(result[index], block)
        note = tables_in(result)[0].get("table_note", "")
        self.assertEqual(note, first_line + "\n" + continuation)
        self.assertNotIn("Ordinary next paragraph.", note)

    def test_note_shared_by_two_tables_is_not_automatically_assigned(self):
        shared_note = NOTE + "Potentially shared conditions."
        blocks = [
            table_block(1, [50, 100, 350, 160]),
            text_block(shared_note, [50, 175, 300, 185]),
            table_block(2, [50, 200, 350, 260]),
        ]
        tables = tables_in(bind_table_context(blocks))
        self.assertEqual(len(tables), 2)
        self.assertTrue(all(not table.get("table_note", "") for table in tables))

    def test_unconfirmed_note_continuation_does_not_bind_a_partial_condition(self):
        for continuation_bbox in ([50, 238, 340, 248], [50, 224, 340, 234]):
            with self.subTest(bbox=continuation_bbox):
                first_line = NOTE + "Personal customers only."
                continuation = "Do not apply to corporate customers."
                blocks = [
                    table_block(),
                    text_block(first_line, [50, 215, 300, 225], group=7),
                    text_block(continuation, continuation_bbox, group=7),
                ]
                result = bind_table_context(blocks)
                self.assertFalse(tables_in(result)[0].get("table_note", ""))
                self.assertEqual([block["text"] for block in result[1:]],
                                 [first_line, continuation])

    def test_explicit_title_and_note_markers_require_real_boundaries(self):
        titles = [
            "\u88681 Loan rules",
            "\u8868\u4e00\uff1aLoan rules",
            "\u9644\u88681 Loan rules",
            "Table 1: Loan rules",
        ]
        for title in titles:
            with self.subTest(title=title):
                blocks = [text_block(title, [50, 80, 280, 90]), table_block()]
                self.assertEqual(tables_in(bind_table_context(blocks))[0].get("table_title"), title)

        for invalid in ("Table 1has conditions", "\u88681\u7684\u5185\u5bb9\u5982\u4e0b"):
            with self.subTest(invalid_title=invalid):
                blocks = [text_block(invalid, [50, 80, 280, 90]), table_block()]
                self.assertFalse(tables_in(bind_table_context(blocks))[0].get("table_title", ""))

        markers = ["\u6ce8", "\u5907\u6ce8", "\u8bf4\u660e", "\u5355\u4f4d",
                   "\u9002\u7528\u6761\u4ef6", "\u9002\u7528\u8303\u56f4"]
        for marker in markers:
            note = marker + ": Personal customers only."
            for side in ("before", "after"):
                with self.subTest(marker=marker, side=side):
                    candidate = text_block(note, [50, 80, 300, 90] if side == "before"
                                           else [50, 210, 300, 220])
                    blocks = [candidate, table_block()] if side == "before" else [table_block(), candidate]
                    self.assertEqual(tables_in(bind_table_context(blocks))[0].get("table_note"), note)

    def test_long_table_repeats_context_and_counts_final_heading_prefix_in_budget(self):
        title = "Table 1: Consumer loan documentation"
        note = NOTE + "Only personal loans with complete supporting documentation."
        rows = [[f"{number:03d}", "Evidence " + "required." * 5] for number in range(1, 9)]
        common = {"source": "context.pdf", "document_id": "context-test", "file_type": "pdf",
                  "page_number": 1}
        documents = [
            Document(page_content="# Retail lending\nRules for products.", metadata=dict(common)),
            Document(page_content="Raw table placeholder", metadata={
                **common, "content_type": "table", "table_title": title, "table_note": note,
                "table_data": {"headers": ["Code", "Description"], "rows": rows},
            }),
        ]
        # Exactly two rows fit before the chapter prefix is reserved. A caller
        # that forgets reserved_chars would now exceed the final-content budget.
        probe = TableSplitter(max_chars=10000).split(
            ["Code", "Description"], rows[:2],
            metadata={"table_title": title, "table_note": note},
        )
        budget = len(probe[0].page_content)
        chunks = StructuredDocumentSplitter(chunk_size=budget, chunk_overlap=0).split_documents(documents)
        tables = [doc for doc in chunks if doc.metadata.get("content_type") == "table"]
        self.assertGreater(len(tables), 1)
        covered = []
        for chunk in tables:
            self.assertEqual(chunk.metadata["heading_path"], ["Retail lending"])
            self.assertTrue(chunk.page_content.startswith("\u3010\u6807\u9898\u8def\u5f84\u3011Retail lending\n"))
            self.assertEqual(chunk.page_content.count(title), 1)
            self.assertEqual(chunk.page_content.count(note), 1)
            self.assertLess(chunk.page_content.index(title), chunk.page_content.index("| Code | Description |"))
            self.assertGreater(chunk.page_content.index(note), chunk.page_content.rindex("|"))
            self.assertLessEqual(len(chunk.page_content), budget)
            self.assertFalse(chunk.metadata["oversized"])
            start, end = chunk.metadata["row_start"], chunk.metadata["row_end"]
            covered.extend(range(start, end + 1))
            for row_number in range(start, end + 1):
                code, description = rows[row_number - 1]
                self.assertIn(f"| {code} | {description} |", chunk.page_content)
        self.assertEqual(covered, list(range(1, len(rows) + 1)))

    def test_oversized_context_keeps_all_rows_and_marks_actual_plus_reserved_size(self):
        title = "Table 1: " + "Important title " * 12
        note = NOTE + "Do not omit this applicability condition. " * 12
        rows = [[f"{number:03d}", "Loan"] for number in range(1, 4)]
        reserved = 30
        chunks = TableSplitter(max_chars=80).split(
            ["Code", "Product"], rows,
            metadata={"table_title": title, "table_note": note},
            reserved_chars=reserved,
        )
        self.assertEqual(len(chunks), len(rows))
        covered = []
        for chunk in chunks:
            self.assertIn(title, chunk.page_content)
            self.assertIn(note, chunk.page_content)
            self.assertTrue(chunk.metadata["oversized"])
            self.assertGreater(len(chunk.page_content) + reserved, 80)
            start, end = chunk.metadata["row_start"], chunk.metadata["row_end"]
            self.assertEqual(start, end)
            covered.extend(range(start, end + 1))
            self.assertIn(f"| {start:03d} | Loan |", chunk.page_content)
        self.assertEqual(covered, [1, 2, 3])

        # Reservation alone must also change the flag, even when the emitted
        # text itself fits. The reserved prefix is added by the outer splitter.
        probe = TableSplitter(max_chars=10000).split(["Code", "Product"], rows[:1])[0]
        limit = len(probe.page_content) + 5
        reserved_only = TableSplitter(max_chars=limit).split(
            ["Code", "Product"], rows[:1], reserved_chars=10
        )[0]
        self.assertLessEqual(len(reserved_only.page_content), limit)
        self.assertTrue(reserved_only.metadata["oversized"])
        self.assertGreater(len(reserved_only.page_content) + 10, limit)


if __name__ == "__main__":
    unittest.main()
