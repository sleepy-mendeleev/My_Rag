"""提取文字型 PDF 中普通有边框表格，并保守关联近邻说明。"""
import re


def extract_pdf_tables(file_path: str) -> list[dict]:
    import pdfplumber

    results = []
    settings = {
        "vertical_strategy": "lines",
        "horizontal_strategy": "lines",
    }

    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            tables = page.find_tables(table_settings=settings)

            for number, table in enumerate(tables, 1):
                data = table.extract()
                if not data:
                    raise ValueError(
                        f"第 {page.page_number} 页第 {number} 张表格无法提取数据"
                    )

                # 本阶段约定：第一行为表头，其余为数据行。
                headers, rows = data[0], data[1:]

                needs_review = (
                    not headers
                    or not rows
                    or any(
                        value is None or not str(value).strip()
                        for value in headers
                    )
                    or any(
                        value is None
                        for row in data
                        for value in row
                    )
                    or any(
                        len(row) != len(headers)
                        for row in rows
                    )
                )

                results.append({
                    "source": str(file_path),
                    "page_number": page.page_number,
                    "table_number": number,
                    "bbox": list(table.bbox),
                    "headers": headers,
                    "rows": rows,
                    "needs_review": needs_review,
                })

    return results


def bind_table_context(blocks: list[dict]) -> list[dict]:
    """给同页已排序的表格块关联表题和注释，不删除或改写正文。

    只接受显式编号表题、带冒号的说明；不跨普通正文或其他表格搜索。
    原生块拆成多行时，以 text_block 和几何连续性构建临时段落视图，
    供匹配使用，返回结果仍保留全部原始块及其原始 text。
    """
    # 单位为 PDF 坐标中的点；40pt 允许一到两行的表前/表后留白。
    first_gap = 40.0
    continuation_gap = 12.0
    containment = 0.8
    numbers = r"[0-9零〇一二三四五六七八九十百千万两]+"
    caption = re.compile(
        rf"^(?:附?表\s*{numbers}(?:[-.．－]{numbers})*"
        rf"|Table\s+\d+(?:[.-]\d+)*)(?=\s|[:：])",
        re.I,
    )
    note = re.compile(r"^(?:注|备注|说明|单位|适用条件|适用范围)\s*[:：]")
    heading = re.compile(
        rf"^(?:#{{1,6}}\s|第{numbers}[章节条]|chapter\b|section\b)",
        re.I,
    )

    def kind(text):
        text = text.strip()
        if caption.match(text):
            return "title"
        if note.match(text):
            return "note"
        return None

    def horizontal_overlap(a, b):
        return max(0.0, min(a[2], b[2]) - max(a[0], b[0]))

    def inside_table_width(candidate, table):
        width = candidate[2] - candidate[0]
        return width > 0 and horizontal_overlap(candidate, table) >= containment * width

    # 复制外层字典，确保添加关联字段不会修改调用方的原始 blocks。
    result = [dict(block) for block in blocks]
    paragraphs = []

    for index, block in enumerate(blocks):
        if "table_data" in block:
            paragraphs.append({"table_index": index, "bbox": list(block["bbox"])})
            continue

        text = block["text"].strip()
        bbox = block["bbox"]
        identity = block.get("text_block")
        previous = paragraphs[-1] if paragraphs else None
        can_join = False

        if (
            previous is not None
            and "table_index" not in previous
            and type(identity) is int
            and previous["text_block"] == identity
            # 新的显式标记、章节/条款必须另起段，不能被当成上一段续行。
            and kind(text) is None
            and not heading.match(text)
        ):
            last_bbox = previous["last_bbox"]
            gap = bbox[1] - last_bbox[3]
            shorter_width = min(bbox[2] - bbox[0], last_bbox[2] - last_bbox[0])
            can_join = (
                0 <= gap <= continuation_gap
                and shorter_width > 0
                and horizontal_overlap(bbox, last_bbox) >= 0.5 * shorter_width
            )

        if can_join:
            previous["text"] += "\n" + text
            previous["bbox"] = [
                min(previous["bbox"][0], bbox[0]),
                min(previous["bbox"][1], bbox[1]),
                max(previous["bbox"][2], bbox[2]),
                max(previous["bbox"][3], bbox[3]),
            ]
            previous["last_bbox"] = list(bbox)
        else:
            # 同一原生段落仍有续文，却无法可靠拼接时，不能只绑定前半段。
            if (
                previous is not None
                and "table_index" not in previous
                and type(identity) is int
                and previous["text_block"] == identity
                and kind(text) is None
                and not heading.match(text)
            ):
                previous["incomplete"] = True
            paragraphs.append({
                "text": text,
                "bbox": list(bbox),
                "last_bbox": list(bbox),
                "text_block": identity,
            })

    proposals = {}
    owners = {}

    for table_position, table in enumerate(paragraphs):
        if "table_index" not in table:
            continue

        matches = []
        # 向上允许连续的注释，最后是最近的一个表题；向下只接受注释。
        for direction in (-1, 1):
            position = table_position + direction
            reference = table["bbox"]
            limit = first_gap

            while 0 <= position < len(paragraphs):
                candidate = paragraphs[position]
                if "table_index" in candidate:
                    break

                candidate_kind = kind(candidate["text"])
                if candidate.get("incomplete"):
                    break
                if candidate_kind is None or (direction == 1 and candidate_kind != "note"):
                    break

                bbox = candidate["bbox"]
                gap = reference[1] - bbox[3] if direction == -1 else bbox[1] - reference[3]
                if not 0 <= gap <= limit or not inside_table_width(bbox, table["bbox"]):
                    break

                matches.append((position, candidate_kind))
                owners.setdefault(position, set()).add(table_position)
                if candidate_kind == "title":
                    break

                reference = bbox
                limit = continuation_gap
                position += direction

        proposals[table_position] = matches

    for table_position, matches in proposals.items():
        # 同一段若同时符合两张表，不能靠遍历先后决定它的归属。
        unambiguous = [
            (position, candidate_kind)
            for position, candidate_kind in sorted(matches)
            if len(owners[position]) == 1
        ]
        titles = [paragraphs[position]["text"] for position, candidate_kind in unambiguous
                  if candidate_kind == "title"]
        notes = [paragraphs[position]["text"] for position, candidate_kind in unambiguous
                 if candidate_kind == "note"]
        target = result[paragraphs[table_position]["table_index"]]
        if titles:
            target["table_title"] = titles[0]
        if notes:
            target["table_note"] = "\n".join(notes)

    return result
