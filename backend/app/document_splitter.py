"""Rule-based chapter/article splitting for extracted text, without OCR or LLM calls."""
import hashlib
import re
from .table_splitter import TableSplitter
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter


class StructuredDocumentSplitter:
    def __init__(self, chunk_size=500, chunk_overlap=50):
        self.table_splitter = TableSplitter(max_chars=chunk_size)
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size, chunk_overlap=chunk_overlap,
            separators=['\n\n', '\n', '。', '！', '？', '；', '，', ' ', ''])

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

    def split_documents(self, documents):
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
                segments.append(Document(page_content=doc.page_content, metadata=dict(doc.metadata)))
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

        result = []
        for segment_number, segment in enumerate(segments):
            base_metadata = dict(segment.metadata)
            document_id = base_metadata.get('document_id') or hashlib.sha256(
                str(base_metadata.get('source', '')).encode()).hexdigest()
            section_id = hashlib.sha256(
                f'{document_id}:{segment_number}'.encode()).hexdigest()

            table_data = base_metadata.pop('table_data', None)
            is_table = base_metadata.get('content_type') == 'table'

            if is_table:
                if table_data is None:
                    raise ValueError('表格缺少表头和数据行')

                base_metadata['table_id'] = section_id
                pieces = self.table_splitter.split(
                    table_data['headers'],
                    table_data['rows'],
                    metadata=base_metadata,
                )
            else:
                pieces = [
                    Document(page_content=body, metadata=dict(base_metadata))
                    for body in self.splitter.split_text(segment.page_content)
                ]

            title_path = base_metadata.get('heading_path', [])
            if base_metadata.get('article'):
                title_path = title_path + [base_metadata['article']]
            prefix = ' / '.join(title_path)

            for chunk_index, piece in enumerate(pieces):
                body = piece.page_content
                metadata = dict(piece.metadata)
                metadata.update({
                    'document_id': document_id,
                    'section_id': section_id,
                    'chunk_index': chunk_index,
                    'chunk_id': hashlib.sha256(
                        f'{section_id}:{chunk_index}:{body}'.encode()).hexdigest(),
                    'splitter_version': 'table-v1' if is_table else 'structure-v1',
                })

                content = f'【标题路径】{prefix}\n{body}' if prefix else body
                result.append(Document(page_content=content, metadata=metadata))

        return result
