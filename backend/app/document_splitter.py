"""结构分段、语义分组与长度兜底。"""
import hashlib
import logging
import re
from math import isfinite

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from .semantic_splitter import semantic_split_text, split_semantic_units
from .table_splitter import TableSplitter
from .chunk_postprocessor import postprocess_chunks

logger = logging.getLogger(__name__)


class StructuredDocumentSplitter:
    def __init__(
        self,
        chunk_size=500,
        chunk_overlap=50,
        embeddings=None,
        semantic_threshold=None,
    ):
        if chunk_size <= 0:
            raise ValueError("chunk_size 必须大于 0")

        if not 0 <= chunk_overlap < chunk_size:
            raise ValueError("chunk_overlap 必须非负且小于 chunk_size")

        if embeddings is not None and (
            semantic_threshold is None
            or not isfinite(semantic_threshold)
            or not -1 <= semantic_threshold <= 1
        ):
            raise ValueError("启用语义切分时，必须提供有效的相似度阈值")

        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.embeddings = embeddings
        self.semantic_threshold = semantic_threshold
        self.table_splitter = TableSplitter(max_chars=chunk_size)

    def _split_body(self, text, reserved_chars=0, preserve_short=False):
        """返回正文片段及实际使用的切分策略版本。"""
        budget = self.chunk_size - reserved_chars
        if budget <= 0:
            raise ValueError("标题前缀已占满 chunk_size，无法容纳正文")

        if not text.strip():
            return [], "structure-v2"

        groups = [text]
        version = "structure-v2"

        use_semantic = (
            self.embeddings is not None
            and not (preserve_short and len(text) <= budget)
            and len(split_semantic_units(text)) > 1
        )

        if use_semantic:
            try:
                groups = semantic_split_text(
                    text,
                    self.embeddings,
                    self.semantic_threshold,
                )
            except Exception as error:
                logger.warning(
                    "语义切分失败，回退递归切分：%s", error
                )
            else:
                version = "semantic-v1"

        length_splitter = RecursiveCharacterTextSplitter(
            chunk_size=budget,
            chunk_overlap=min(self.chunk_overlap, budget - 1),
            separators=[
                "\n\n", "\n", "。", "！", "？", "；", "，", " ", ""
            ],
        )

        bodies = []
        for group in groups:
            if not group.strip():
                continue

            if len(group) <= budget:
                bodies.append(group)
            else:
                bodies.extend(length_splitter.split_text(group))

        return bodies, version
    
    @staticmethod
    def heading(line):
        """Conservative explicit headings; font/layout based detection comes later."""
        numbers = r'[零〇一二三四五六七八九十百千万两\d]+'
        match = re.match(r'^(#{1,6})\s+(.+)$', line)
        if match:
            return len(match[1]), match[2].strip()
        match = re.match(rf'^第{numbers}([章节])(?:\s+.*)?$', line)
        if match and len(line) <= 100:
            return (1 if match[1] == '章' else 2), line
        return None

    def _build_segments(self, documents):
        """按标题、条款和表格边界组织结构段。"""
        segments = []
        buffer = []
        headings = {}
        article = ''
        metadata = None
        current_identity = None

        def flush():
            nonlocal buffer, metadata
            text = '\n'.join(buffer).strip()
            # A bare heading has no answer evidence; keep it in metadata instead.
            has_body = any(line.strip() and not self.heading(line.strip()) and
                           not re.fullmatch(r'第[零〇一二三四五六七八九十百千万两\d]+条', line.strip())
                           for line in buffer)
            if text and has_body and metadata is not None:
                segments.append(Document(page_content=text, metadata=dict(metadata)))
            buffer, metadata = [], None

        for doc in documents:
            identity = (doc.metadata.get('document_id'), doc.metadata.get('source'))
            if identity != current_identity:
                flush()
                headings, article = {}, ''
                current_identity = identity
            # Each spreadsheet record remains its own segment, outside heading parsing.
            if (doc.metadata.get('content_type') == 'table' or
                    doc.metadata.get('file_type') in ('csv', 'excel')):
                flush()

                table_metadata = dict(doc.metadata)

                if table_metadata.get('file_type') in ('docx', 'pdf'):
                    table_metadata.update({
                        'heading_path': [
                            headings[key] for key in sorted(headings)
                        ],
                        'article': article,
                    })

                segments.append(Document(
                    page_content=doc.page_content,
                    metadata=table_metadata,
                ))
                continue
            for original_line in doc.page_content.splitlines():
                line = original_line.strip()
                found_heading = self.heading(line)
                found_article = re.match(r'^(第[零〇一二三四五六七八九十百千万两\d]+条)(?:\s*(.*))$', line)
                if found_heading:
                    flush()
                    level, title = found_heading
                    headings = {key: value for key, value in headings.items() if key < level}
                    headings[level] = title
                    article = ''
                elif found_article:
                    flush()
                    article = found_article[1]
                if not line and not buffer:
                    continue
                if metadata is None:
                    metadata = dict(doc.metadata)
                    metadata.update({'heading_path': [headings[key] for key in sorted(headings)],
                                     'article': article})
                    if 'page_number' in doc.metadata:
                        metadata['page_start'] = doc.metadata['page_number']
                if 'page_number' in doc.metadata:
                    metadata['page_end'] = doc.metadata['page_number']
                buffer.append(original_line)
        flush()
        return segments

    def split_documents(self, documents):
        """先组织结构段，再分别切分正文与表格。"""
        segments = self._build_segments(documents)

        result = []
        for segment_number, segment in enumerate(segments):
            base_metadata = dict(segment.metadata)
            document_id = base_metadata.get('document_id') or hashlib.sha256(
                str(base_metadata.get('source', '')).encode()
            ).hexdigest()
            section_id = hashlib.sha256(
                f'{document_id}:{segment_number}'.encode()
            ).hexdigest()

            table_data = base_metadata.pop('table_data', None)
            is_table = base_metadata.get('content_type') == 'table'

            title_path = base_metadata.get('heading_path', [])
            if base_metadata.get('article'):
                title_path = title_path + [base_metadata['article']]

            prefix = ' / '.join(title_path)
            prefix_text = f'【标题路径】{prefix}\n' if prefix else ''

            if is_table:
                if table_data is None:
                    raise ValueError('表格缺少表头和数据行')

                splitter_version = "table-v1"
                base_metadata['table_id'] = section_id

                pieces = self.table_splitter.split(
                    table_data['headers'],
                    table_data['rows'],
                    metadata=base_metadata,
                    reserved_chars=len(prefix_text),
                )
            else:
                bodies, splitter_version = self._split_body(
                    segment.page_content,
                    reserved_chars=len(prefix_text),
                    preserve_short=bool(base_metadata.get('article')),
                )

                pieces = [
                    Document(page_content=body, metadata=dict(base_metadata))
                    for body in bodies
                ]

            for chunk_index, piece in enumerate(pieces):
                body = piece.page_content
                metadata = dict(piece.metadata)
                metadata.update({
                    'document_id': document_id,
                    'section_id': section_id,
                    'chunk_index': chunk_index,
                    'chunk_id': hashlib.sha256(
                        f'{section_id}:{chunk_index}:{body}'.encode()
                    ).hexdigest(),
                    'splitter_version': splitter_version,
                })

                content = prefix_text + body

                if not is_table and len(content) > self.chunk_size:
                    raise ValueError("正文片段包含标题后超过长度上限")

                result.append(Document(
                    page_content=content,
                    metadata=metadata,
                ))

        return postprocess_chunks(
            result,
            max_chars=self.chunk_size,
        )