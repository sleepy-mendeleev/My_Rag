"""提取 PDF 正文和普通表格，恢复阅读顺序。"""
from pathlib import Path

from .pdf_layout import order_text_blocks
from .pdf_margins import filter_repeated_margins
from .pdf_tables import bind_table_context, extract_pdf_tables
from .pdf_ocr import create_ocr_textpage


def _body_blocks(page, table_boxes,textpage=None):
    """只保留表格范围外的字符，避免误删同块中的表外正文。"""
    import pymupdf

    if not table_boxes:
        return [
            {"bbox": list(item[:4]), "text": item[4].strip()}
            for item in page.get_text(
                "blocks",
                sort=True,
                textpage=textpage,
            )
            if item[6] == 0 and item[4].strip()
        ]    

    blocks = []

    def emit(chars, block_number):
        text = "".join(char["c"] for char in chars).strip()
        if text:
            boxes = [char["bbox"] for char in chars]
            blocks.append({
                "bbox": [
                    min(box[0] for box in boxes),
                    min(box[1] for box in boxes),
                    max(box[2] for box in boxes),
                    max(box[3] for box in boxes),
                ],
                "text": text,
                "text_block": block_number,
            })

    flags = pymupdf.TEXTFLAGS_RAWDICT & ~pymupdf.TEXT_PRESERVE_IMAGES
    for block_number, block in enumerate(
        page.get_text(
            "rawdict",
            flags=flags,
            textpage=textpage,
        )["blocks"]
    ):
        if block["type"] != 0:
            continue
        for line in block["lines"]:
            kept = []
            for span in line["spans"]:
                for char in span["chars"]:
                    x0, y0, x1, y1 = char["bbox"]
                    x, y = (x0 + x1) / 2, (y0 + y1) / 2
                    if any(a <= x <= c and b <= y <= d
                           for a, b, c, d in table_boxes):
                        emit(kept, block_number)
                        kept = []
                    else:
                        kept.append(char)
            emit(kept, block_number)

    return blocks


def extract_pdf_pages(file_path: str) -> list[dict]:
    import pymupdf

    pages = []

    with pymupdf.open(file_path) as pdf:
        if pdf.needs_pass:
            raise ValueError("PDF 已加密，请先提供可读取的文件")

        tables_by_page = {}

        for table in extract_pdf_tables(file_path):
            if table["needs_review"]:
                raise ValueError(
                    f'PDF 第 {table["page_number"]} 页第 '
                    f'{table["table_number"]} 张表格结构需检查'
                )

            tables_by_page.setdefault(
                table["page_number"], []
            ).append(table)

        for page in pdf:
            tables = tables_by_page.get(page.number + 1, [])
            if tables and (
                page.rotation
                or page.cropbox != page.mediabox
                or page.mediabox.x0 != 0
                or page.mediabox.y0 != 0
            ):
                raise ValueError(
                    f"PDF 第 {page.number + 1} 页含旋转或裁剪，"
                    "表格坐标尚未适配，请先核对"
                )

            # 在排除表内文字前记录，纯表格页也有有效原生文字。
                        # 记录原始页面是否存在文字层。
            
            has_native_text = bool(page.get_text("text").strip())
            has_images = bool(page.get_image_info())

            textpage = None
            extraction_method = "native"

            if not has_native_text:
                textpage = create_ocr_textpage(page, full=True)
                extraction_method = "ocr"

            elif has_images:
                textpage = create_ocr_textpage(page, full=False)
                extraction_method = "mixed"

            boxes = [table["bbox"] for table in tables]
            blocks = _body_blocks(
                page,
                boxes,
                textpage=textpage,
            )

            if extraction_method == "ocr" and not blocks and not tables:
                raise ValueError(
                    f"PDF 第 {page.number + 1} 页 OCR 未识别到有效文字，"
                    "请检查是否为空白页或图片不清晰"
                )

            pages.append({
                "page_number": page.number + 1,
                "width": page.cropbox.width,
                "height": page.cropbox.height,
                "has_native_text": has_native_text,
                "extraction_method": extraction_method,
                "blocks": blocks,
                "tables": tables,
            })

    if not pages:
        raise ValueError(f"PDF 没有页面：{Path(file_path).name}")

    # 收齐各页后，才能判断哪些内容跨页重复。
    pages = filter_repeated_margins(pages)

    if not any(page["blocks"] or page["tables"] for page in pages):
        raise ValueError(
            "PDF 页眉页脚清理后没有有效正文，请核对原文和过滤规则"
        )

    # 页边清理后再加入表格，避免将表格当作页眉页脚删除。
    for page in pages:
        for table in page["tables"]:
            page["blocks"].append({
                "bbox": table["bbox"],
                "text": "\n".join(
                    "\t".join(row)
                    for row in [table["headers"], *table["rows"]]
                ),
                "content_type": "table",
                "table_number": table["table_number"],
                "table_data": {
                    "headers": table["headers"],
                    "rows": table["rows"],
                },
            })
        page["blocks"] = order_text_blocks(
            page["blocks"], page["width"]
        )
        page["blocks"] = bind_table_context(page["blocks"])

    return pages
