"""保守过滤跨页重复的文字页眉和页脚。"""
import math
import re
from collections import defaultdict


_PROTECTED_PREFIX = re.compile(
    r"^(?:#{1,6}\s|第[零〇一二三四五六七八九十百千万两\d]+[章节条]"
    r"|附?表|图|注[：:]|备注[：:]|说明[：:]|单位[：:]"
    r"|适用条件[：:]|适用范围[：:]"
    r"|chapter\b|section\b|table\b|figure\b|notes?\b)",
    re.I,
)


def _margin_key(page, block, total_pages):
    x0, y0, x1, y1 = block["bbox"]
    width, height = page["width"], page["height"]

    if y1 <= height * 0.08:
        side = "top"
    elif y0 >= height * 0.92:
        side = "bottom"
    else:
        return None

    lines = [
        re.sub(r"\s+", " ", line).strip()
        for line in block["text"].splitlines() if line.strip()
    ]
    if not lines or len(lines) > 2 or sum(map(len, lines)) > 100:
        return None
    if y1 - y0 > height * 0.03:
        return None

    normalized = []

    for line in lines:
        # 可识别的结构标题和注释优先保留。
        if _PROTECTED_PREFIX.match(line):
            return None

        number = (
            re.fullmatch(r"(\d+)\s*[/／]\s*(\d+)", line)
            or re.fullmatch(
                r"第\s*(\d+)\s*页(?:\s*[/／，,]?\s*共\s*(\d+)\s*页)?",
                line,
            )
            or re.fullmatch(
                r"Page\s+(\d+)(?:\s+of\s+(\d+))?", line, re.I
            )
        )

        if number and int(number[1]) == page["page_number"] and (
            number[2] is None or int(number[2]) == total_pages
        ):
            normalized.append("<PAGE>")
        elif re.search(r"\d", line):
            # 保护版本号、日期、金额和编号。
            return None
        else:
            normalized.append(line)

    return side, "\n".join(normalized)


def filter_repeated_margins(pages):
    if len(pages) < 2:
        return pages

    groups = defaultdict(list)

    for page_index, page in enumerate(pages):
        # 有表页的原生段落会拆成多行；注释续行应和首行一起保留。
        # ID 只在当前页内有效，缺少 ID 的块不能被视作同一个段落。
        protected_blocks = {
            block["text_block"]
            for block in page["blocks"]
            if type(block.get("text_block")) is int
            and any(_PROTECTED_PREFIX.match(line.strip())
                    for line in block["text"].splitlines())
        }
        for block_index, block in enumerate(page["blocks"]):
            identity = block.get("text_block")
            if type(identity) is int and identity in protected_blocks:
                continue
            key = _margin_key(page, block, len(pages))

            if key is not None:
                x0, y0, x1, y1 = block["bbox"]
                groups[key].append((
                    page_index,
                    block_index,
                    (x0 + x1) / (2 * page["width"]),
                    (y0 + y1) / (2 * page["height"]),
                ))

    minimum_pages = max(2, math.ceil(len(pages) * 0.6))
    removed = set()

    for occurrences in groups.values():
        # 按不同页面数统计，避免一页多次出现造成误判。
        if len({item[0] for item in occurrences}) < minimum_pages:
            continue

        xs = [item[2] for item in occurrences]
        ys = [item[3] for item in occurrences]

        if max(xs) - min(xs) > 0.02 or max(ys) - min(ys) > 0.01:
            continue

        removed.update((item[0], item[1]) for item in occurrences)

    return [
        {
            **page,
            "blocks": [
                block
                for block_index, block in enumerate(page["blocks"])
                if (page_index, block_index) not in removed
            ],
        }
        for page_index, page in enumerate(pages)
    ]
