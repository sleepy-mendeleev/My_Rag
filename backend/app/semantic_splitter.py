"""正文语义切分使用的基础函数。"""
from math import fsum, hypot, isfinite
import re


def cosine_similarity(
    vector_a: list[float],
    vector_b: list[float],
) -> float:
    """计算两个非零向量的余弦相似度。"""
    if not vector_a or not vector_b:
        raise ValueError("向量不能为空")

    if len(vector_a) != len(vector_b):
        raise ValueError("两个向量的维度必须一致")

    for vector in (vector_a, vector_b):
        if not all(isfinite(value) for value in vector):
            raise ValueError("向量包含非有限数值")

    norm_a = hypot(*vector_a)
    norm_b = hypot(*vector_b)

    if norm_a == 0 or norm_b == 0:
        raise ValueError("零向量无法计算余弦相似度")

    if not isfinite(norm_a) or not isfinite(norm_b):
        raise ValueError("向量范数超出可计算范围")

    score = fsum(
        (a / norm_a) * (b / norm_b)
        for a, b in zip(vector_a, vector_b)
    )

    # 限制浮点计算可能产生的微小越界。
    return max(-1.0, min(1.0, score))

_SENTENCE_BOUNDARY = re.compile(
    r"""[。！？]+[”’」』"'）)】》]*|\r?\n(?:[ \t]*\r?\n)+"""
)

_PROTECTED_STRUCTURE = re.compile(
    r"`|^ {0,3}~{3,}|^(?: {4}|\t)"
    r"|^[ \t]*(?:[-+*][ \t]+|\d+[.)][ \t]+"
    r"|\d+、|[一二三四五六七八九十百]+、)"
    r"|\$|\\\[|\\\(",
    re.MULTILINE,
)


def split_semantic_units(text: str) -> list[str]:
    """划分普通中文正文，同时保留原始文字和空白。"""
    if not text:
        return []

    # 首版对明确的代码、列表和公式标记采取保守处理。
    if _PROTECTED_STRUCTURE.search(text):
        return [text]

    units = []
    start = 0

    for match in _SENTENCE_BOUNDARY.finditer(text):
        end = match.end()
        piece = text[start:end]

        # 空白附到相邻单元，不单独生成空白单元。
        if not piece.strip():
            if units:
                units[-1] += piece
                start = end
            continue

        units.append(piece)
        start = end

    # 保留最后一段，以及原文末尾的空白。
    tail = text[start:]
    if tail:
        if units and not tail.strip():
            units[-1] += tail
        else:
            units.append(tail)

    return units

def group_semantic_units(
    units: list[str],
    vectors: list[list[float]],
    similarity_threshold: float,
) -> list[str]:
    """根据相邻单元的余弦相似度分组，保留原文。"""
    if (
        not isfinite(similarity_threshold)
        or not -1 <= similarity_threshold <= 1
    ):
        raise ValueError("相似度阈值必须是 -1 到 1 之间的有限数值")

    if len(units) != len(vectors):
        raise ValueError("文本单元与向量的数量必须一致")

    if not units:
        return []

    if len(units) == 1:
        cosine_similarity(vectors[0], vectors[0])
        return [units[0]]

    groups = []
    current = [units[0]]

    for index in range(1, len(units)):
        score = cosine_similarity(
            vectors[index - 1],
            vectors[index],
        )

        if score < similarity_threshold:
            groups.append("".join(current))
            current = []

        current.append(units[index])

    groups.append("".join(current))
    return groups

def semantic_split_text(
    text: str,
    embeddings,
    similarity_threshold: float,
) -> list[str]:
    """生成文本单元，获取向量，再按相邻相似度分组。"""
    if (
        not isfinite(similarity_threshold)
        or not -1 <= similarity_threshold <= 1
    ):
        raise ValueError("相似度阈值必须是 -1 到 1 之间的有限数值")

    units = split_semantic_units(text)

    if len(units) <= 1:
        return units

    vectors = embeddings.embed_documents(units)

    return group_semantic_units(
        units,
        vectors,
        similarity_threshold,
    )