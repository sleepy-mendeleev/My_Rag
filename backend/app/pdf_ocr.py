from pathlib import Path

import pymupdf

def _create_mixed_textpage(
    page: pymupdf.Page,
    tessdata: Path,
) -> pymupdf.TextPage:
    """遮盖已有可读文字的区域，避免 OCR 重复识别。"""

    with pymupdf.open() as temporary_pdf:
        # 只复制当前页，在内存副本上处理。
        temporary_pdf.insert_pdf(
            page.parent,
            from_page=page.number,
            to_page=page.number,
        )
        temporary_page = temporary_pdf[0]

        # 获取原生文字及其位置，不读取图片数据。
        data = page.get_text("dict", flags=0)

        for block in data["blocks"]:
            if block["type"] != 0:
                continue

            for line in block["lines"]:
                for span in line["spans"]:
                    text = span["text"].strip()

                    # 空白或包含无法识别字符的文字，不作为遮盖依据。
                    if not text or "\ufffd" in text:
                        continue

                    temporary_page.draw_rect(
                        span["bbox"],
                        color=None,
                        fill=(1, 1, 1),
                        overlay=True,
                    )

        textpage = temporary_page.get_textpage_ocr(
            language="chi_sim+eng",
            dpi=300,
            full=False,
            tessdata=str(tessdata),
        )

        # 后续解析仍使用原页面读取这份结果。
        textpage.parent = page
        return textpage

def create_ocr_textpage(
    page: pymupdf.Page,
    full: bool = True,
) -> pymupdf.TextPage:
    """执行 OCR，返回包含识别文字及坐标的 TextPage。"""
    project_root = Path(__file__).resolve().parents[2]
    tessdata = project_root / "models" / "tessdata"

    for language in ("chi_sim", "eng"):
        model_file = tessdata / f"{language}.traineddata"
        if not model_file.is_file():
            raise ValueError(f"OCR 缺少语言文件：{model_file}")

    try:
        if not full:
            return _create_mixed_textpage(page, tessdata)
        return page.get_textpage_ocr(
            language="chi_sim+eng",
            dpi=300,
            full=full,
            tessdata=str(tessdata),
        )
    except Exception as error:
        raise ValueError(
            f"PDF 第 {page.number + 1} 页 OCR 识别失败：{error}"
        ) from error