"""Offline parsing, chapter boundaries, provenance and metadata storage checks."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from langchain_core.documents import Document
from backend.app.document_loader import DocumentLoader
from backend.app.document_splitter import StructuredDocumentSplitter
from backend.app.vector_db_manager import VectorDatabaseManager
from pymilvus import DataType


def write_pdf(path, pages):
    """Small real text PDF fixture using built-in PDF operators, no extra packages."""
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>', b'',
               b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>']
    kids = []
    for lines in pages:
        page_id = len(objects) + 1
        kids.append(f'{page_id} 0 R')
        objects.append(f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R >> >> /Contents {page_id + 1} 0 R >>'.encode())
        stream = 'BT /F1 12 Tf 50 750 Td\n' + '\n'.join(f'({line}) Tj 0 -20 Td' for line in lines) + '\nET'
        encoded = stream.encode('ascii')
        objects.append(f'<< /Length {len(encoded)} >>\nstream\n'.encode() + encoded + b'\nendstream')
    objects[1] = f'<< /Type /Pages /Kids [{" ".join(kids)}] /Count {len(kids)} >>'.encode()
    output = b'%PDF-1.4\n'
    offsets = [0]
    for index, obj in enumerate(objects, 1):
        offsets.append(len(output))
        output += f'{index} 0 obj\n'.encode() + obj + b'\nendobj\n'
    xref = len(output)
    output += f'xref\n0 {len(offsets)}\n0000000000 65535 f \n'.encode()
    output += b''.join(f'{offset:010d} 00000 n \n'.encode() for offset in offsets[1:])
    output += f'trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF'.encode()
    path.write_bytes(output)


class DocumentStructureTests(unittest.TestCase):
    def test_title_metadata_and_article_boundaries(self):
        source = Document(page_content='第二章 身份核验\n第一节 柜面业务\n第七条\n身份不一致时应暂停办理。\n第八条\n正常办理。\n第三章 转账业务\n第九条\n提交收款账号。',
                          metadata={'source': 'bank.txt', 'document_id': 'abc'})
        chunks = StructuredDocumentSplitter().split_documents([source])
        seventh = next(doc for doc in chunks if doc.metadata['article'] == '第七条')
        self.assertEqual(seventh.metadata['heading_path'], ['第二章 身份核验', '第一节 柜面业务'])
        self.assertNotIn('第八条', seventh.page_content)
        self.assertEqual(len(chunks), 3)  # Bare headings are metadata, not standalone vectors.
        ninth = next(doc for doc in chunks if doc.metadata['article'] == '第九条')
        self.assertEqual(ninth.metadata['heading_path'], ['第三章 转账业务'])
        self.assertEqual([doc.metadata['chunk_id'] for doc in chunks],
                         [doc.metadata['chunk_id'] for doc in StructuredDocumentSplitter().split_documents([source])])

    def test_long_article_children_inherit_same_section(self):
        doc = Document(page_content='第一章 贷款\n第一条\n' + '普通消费贷需提交材料。' * 60,
                       metadata={'source': 'bank.txt', 'document_id': 'abc'})
        children = [chunk for chunk in StructuredDocumentSplitter(120, 15).split_documents([doc])
                    if chunk.metadata['article'] == '第一条']
        self.assertGreater(len(children), 1)
        self.assertEqual(len({child.metadata['section_id'] for child in children}), 1)
        self.assertTrue(all('【标题路径】第一章 贷款 / 第一条' in child.page_content for child in children))

    def test_real_pdf_cross_page_heading_and_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'sample.pdf'
            write_pdf(path, [['# Chapter', '## Section', 'Body on page one.'], ['Continuation on page two.']])
            documents = DocumentLoader().load_single_file(str(path))
            self.assertEqual([doc.metadata['page_number'] for doc in documents], [1, 2])
            chunks = StructuredDocumentSplitter().split_documents(documents)
            body = next(doc for doc in chunks if 'Continuation' in doc.page_content)
            self.assertEqual(body.metadata['heading_path'], ['Chapter', 'Section'])
            self.assertEqual((body.metadata['page_start'], body.metadata['page_end']), (1, 2))
            self.assertIn('Body on page one.', body.page_content)

    def test_empty_pdf_page_is_not_silently_ingested(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'scan.pdf'
            write_pdf(path, [[]])
            with self.assertRaisesRegex(ValueError, 'OCR'):
                DocumentLoader().load_single_file(str(path))

    def test_loader_identity_is_independent_of_temporary_path(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = [Path(directory) / 'a.txt', Path(directory) / 'b.txt']
            for path in paths:
                path.write_text('第一章 身份核验\n第一条\n有效证件。', encoding='utf-8')
            docs = [DocumentLoader().load_single_file(str(path))[0] for path in paths]
            self.assertEqual(docs[0].metadata['document_id'], docs[1].metadata['document_id'])

    def test_table_rows_are_not_merged_or_interpreted_as_headings(self):
        docs = [Document(page_content='第一章 不是标题\n金额: 100', metadata={'file_type': 'csv', 'row': n}) for n in [0, 1]]
        chunks = StructuredDocumentSplitter().split_documents(docs)
        self.assertEqual([doc.metadata['row'] for doc in chunks], [0, 1])
        self.assertTrue(all(not doc.metadata.get('heading_path') for doc in chunks))

    def test_old_collection_refuses_metadata_loss_without_deleting(self):
        manager = VectorDatabaseManager.__new__(VectorDatabaseManager)
        manager.collection_name = 'agent_rag'
        manager.vectorstore = None
        col = MagicMock()
        col.schema = SimpleNamespace(enable_dynamic_field=False, fields=[SimpleNamespace(name='source', dtype=DataType.VARCHAR)])
        with patch('backend.app.vector_db_manager.utility.has_collection', return_value=True), \
             patch('backend.app.vector_db_manager.Collection', return_value=col), \
             patch('backend.app.vector_db_manager.utility.drop_collection') as drop:
            with self.assertRaisesRegex(ValueError, 'bank_rag_v2'):
                manager.add_documents_to_db([Document(page_content='正文', metadata={'source': 'bank.txt', 'heading_path': ['第一章']})])
            drop.assert_not_called()

    def test_new_collection_enables_dynamic_metadata_and_l2(self):
        manager = VectorDatabaseManager.__new__(VectorDatabaseManager)
        with patch('backend.app.vector_db_manager.utility.has_collection', return_value=False):
            options = manager._milvus_options('bank_rag_v2')
        self.assertTrue(options['enable_dynamic_field'])
        self.assertEqual(options['index_params']['metric_type'], 'L2')

    def test_manager_uses_unified_loader(self):
        manager = VectorDatabaseManager.__new__(VectorDatabaseManager)
        manager.document_loader = MagicMock()
        manager.load_document('bank.pdf')
        manager.document_loader.load_single_file.assert_called_once_with('bank.pdf')

    def test_vector_browser_returns_dynamic_heading_metadata(self):
        manager = VectorDatabaseManager.__new__(VectorDatabaseManager)
        col = MagicMock()
        col.schema = SimpleNamespace(enable_dynamic_field=True, fields=[
            SimpleNamespace(name='pk', dtype=DataType.INT64, is_primary=True),
            SimpleNamespace(name='text', dtype=DataType.VARCHAR, is_primary=False),
            SimpleNamespace(name='vector', dtype=DataType.FLOAT_VECTOR, is_primary=False)])
        col.query.return_value = [{'pk': 123, 'text': '正文', 'vector': [0.1],
                                  'source': 'bank.pdf', 'heading_path': ['第二章'], 'article': '第七条'}]
        with patch('backend.app.vector_db_manager.utility.has_collection', return_value=True), \
             patch('backend.app.vector_db_manager.Collection', return_value=col):
            result = manager.list_vectors('bank_rag_v2')
        self.assertEqual(col.query.call_args.kwargs['output_fields'], ['*'])
        self.assertEqual(result['items'][0]['metadata']['heading_path'], ['第二章'])
        self.assertEqual(result['items'][0]['source'], 'bank.pdf')


if __name__ == '__main__':
    unittest.main()
