"""按完整数据行切分表格，并生成 Markdown 片段。"""
from langchain_core.documents import Document


class TableSplitter:
    def __init__(self, max_chars=500):
        if max_chars <= 0:
            raise ValueError("max_chars 必须大于 0")
        self.max_chars = max_chars

    @staticmethod
    def _format_row(row):
        """把一条数据行转换成 Markdown 表格行。"""
        cells = []

        for value in row:
            text = "" if value is None else str(value)
            text = text.replace("\r\n", "\n").replace("\r", "\n")
            text = text.replace("|", "&#124;").replace("\n", "<br>")
            cells.append(text)

        return "| " + " | ".join(cells) + " |"

    def split(self, headers, rows, metadata=None):
        """按完整行分块；每块重复表头。"""
        if not headers:
            raise ValueError("表格缺少表头")

        rows = list(rows)
        for number, row in enumerate(rows, 1):
            if len(row) != len(headers):
                raise ValueError(f"第 {number} 条数据的列数与表头不一致")

        # 每个片段都带上表头和 Markdown 分隔行。
        prefix = self._format_row(headers) + "\n"
        prefix += self._format_row(["---"] * len(headers))

        chunks = []
        current_rows = []
        current_size = len(prefix)
        row_start = 1

        def emit(row_end):
            """把当前积累的数据行生成一个 Document。"""
            content = prefix + "\n" + "\n".join(current_rows)
            chunk_metadata = dict(metadata or {})

            chunk_metadata.update({
                "content_type": "table",
                "row_start": row_start,
                "row_end": row_end,
                "oversized": len(content) > self.max_chars,
            })

            chunks.append(Document(
                page_content=content,
                metadata=chunk_metadata,
            ))

        for row_number, row in enumerate(rows, 1):
            row_text = self._format_row(row)
            added_size = len(row_text) + 1

            # 当前块已有数据，且放入下一行会超预算，则先输出当前块。
            if current_rows and current_size + added_size > self.max_chars:
                emit(row_number - 1)
                current_rows = []
                current_size = len(prefix)
                row_start = row_number

            current_rows.append(row_text)
            current_size += added_size

        # 输出最后一块。
        if current_rows:
            emit(len(rows))

        return chunks