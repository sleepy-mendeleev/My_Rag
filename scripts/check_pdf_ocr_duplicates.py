from pathlib import Path

import pymupdf

from backend.app.pdf_parser import extract_pdf_pages


def main():
    project_root = Path(__file__).resolve().parents[1]
    source_path = project_root / "data/samples/bank_pdf_demo.pdf"
    target = project_root / "logs/ocr_overlap_demo.pdf"
    target.parent.mkdir(parents=True, exist_ok=True)

    phrase = "应提供有效身份证件"

    with pymupdf.open(source_path) as source:
        original = source[0]
        native_text = "".join(original.get_text("text").split())

        image = original.get_pixmap(dpi=200, alpha=False)

        with pymupdf.open() as output:
            page = output.new_page(
                width=original.rect.width,
                height=original.rect.height,
            )

            # 复制原页面，保留原生文字层。
            page.show_pdf_page(page.rect, source, 0)

            # 在相同位置覆盖该页面的截图。
            page.insert_image(
                page.rect,
                stream=image.tobytes("png"),
            )

            output.save(str(target), deflate=True)

    pages = extract_pdf_pages(str(target))

    parsed_text = "\n".join(
        block["text"]
        for page in pages
        for block in page["blocks"]
    )
    normalized_text = "".join(parsed_text.split())

    print("native_count:", native_text.count(phrase))
    print("parsed_count:", normalized_text.count(phrase))
    print(parsed_text)


if __name__ == "__main__":
    main()