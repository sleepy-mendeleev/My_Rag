"""根据文字块坐标，恢复典型双栏页面的阅读顺序。"""


def order_text_blocks(blocks: list[dict], page_width: float) -> list[dict]:
    position = lambda block: (block["bbox"][1], block["bbox"][0])
    basic = sorted(blocks, key=position)

    # 只用中等宽度的正文寻找栏位，表格仍参与后续排序。
    body = [
        block for block in basic
        if "table_data" not in block and 0.15 * page_width
        <= block["bbox"][2] - block["bbox"][0]
        <= 0.55 * page_width
    ]

    starts = sorted(block["bbox"][0] for block in body)
    gaps = sorted(
        ((right - left, right) for left, right in zip(starts, starts[1:])),
        reverse=True,
    )

    divider = None

    for start_gap, right_start in gaps:
        if start_gap < 0.15 * page_width:
            break

        left = [
            block for block in body
            if block["bbox"][2] <= right_start - 0.02 * page_width
        ]
        right = [
            block for block in body
            if block["bbox"][0] >= right_start
        ]

        if len(left) < 2 or len(right) < 2:
            continue

        # 每栏起点应相对集中，避免把三栏强行并成两栏。
        if any(
            max(item["bbox"][0] for item in group)
            - min(item["bbox"][0] for item in group) > 0.10 * page_width
            for group in (left, right)
        ):
            continue

        # 纵向重叠必须涉及左右各两个不同的块。
        pairs = [
            (i, j)
            for i, a in enumerate(left)
            for j, b in enumerate(right)
            if min(a["bbox"][3], b["bbox"][3])
            > max(a["bbox"][1], b["bbox"][1])
        ]
        if len({i for i, j in pairs}) < 2 or len({j for i, j in pairs}) < 2:
            continue

        divider = (
            max(block["bbox"][2] for block in left) + right_start
        ) / 2
        break

    # 没有可靠双栏证据，沿用基础顺序。
    if divider is None:
        return basic

    column_order = lambda block: (
        block["bbox"][0] >= divider,
        block["bbox"][1],
        block["bbox"][0],
    )
    result, zone = [], []
    last_full_bottom = float("-inf")

    for block in basic:
        x0, y0, x1, y1 = block["bbox"]

        if y0 < last_full_bottom:
            return basic

        if x0 < divider < x1:
            # 与通栏块纵向交叠时，保守回退。
            if any(item["bbox"][3] > y0 for item in zone):
                return basic

            result.extend(sorted(zone, key=column_order))
            result.append(block)
            zone = []
            last_full_bottom = y1
        else:
            zone.append(block)

    result.extend(sorted(zone, key=column_order))
    return result
