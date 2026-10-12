"""Vector management checks using mocks; never connect to or delete real data."""
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from flask import Flask
from pymilvus import DataType
from backend.app import api_integration as api
from backend.app import vector_db_manager as db


class VectorManagementTests(unittest.TestCase):
    def setUp(self):
        self.manager = db.VectorDatabaseManager.__new__(db.VectorDatabaseManager)
        self.primary = SimpleNamespace(name='pk', dtype=DataType.INT64, is_primary=True)
        self.col = MagicMock()
        self.col.schema.fields = [
            self.primary,
            SimpleNamespace(name='text', dtype=DataType.VARCHAR, is_primary=False),
            SimpleNamespace(name='source', dtype=DataType.VARCHAR, is_primary=False),
            SimpleNamespace(name='vector', dtype=DataType.FLOAT_VECTOR, is_primary=False),
        ]

    def test_int64_id_is_not_rounded_and_vectors_are_returned(self):
        self.col.query.return_value = [
            {'pk': 469553067275599162, 'text': '测试条款', 'source': 'test.pdf', 'vector': [0.1, 0.2]},
            {'pk': 469553067275599163, 'text': '下一条', 'source': 'test.pdf', 'vector': [0.3, 0.4]},
        ]
        with patch.object(db.utility, 'has_collection', return_value=True), patch.object(db, 'Collection', return_value=self.col):
            result = self.manager.list_vectors('agent_rag', limit=1)
        self.assertEqual(result['items'][0]['id'], '469553067275599162')
        self.assertEqual(result['items'][0]['vector'], [0.1, 0.2])
        self.assertEqual(result['items'][0]['dimension'], 2)
        self.assertTrue(result['has_more'])
        self.assertEqual(self.col.query.call_args.kwargs['consistency_level'], 'Strong')

    def test_missing_collection_is_empty(self):
        with patch.object(db.utility, 'has_collection', return_value=False):
            result = self.manager.list_vectors('agent_rag')
        self.assertEqual(result['items'], [])
        self.assertFalse(result['collection_exists'])

    def test_invalid_pagination_and_collection_are_rejected(self):
        for kwargs in [{'offset': -1}, {'limit': 0}, {'limit': 51}, {'offset': 16380}]:
            with self.assertRaises(ValueError):
                self.manager.list_vectors('agent_rag', **kwargs)
        with self.assertRaises(ValueError):
            self.manager.list_vectors('bad;collection')

    def test_delete_only_targets_exact_id(self):
        self.col.query.return_value = [{'pk': 469553067275599162}]
        with patch.object(db.utility, 'has_collection', return_value=True), patch.object(db, 'Collection', return_value=self.col):
            self.assertTrue(self.manager.delete_vector('agent_rag', '469553067275599162'))
        self.col.delete.assert_called_once_with(expr='pk == 469553067275599162', timeout=15)

    def test_nonexistent_id_does_not_delete(self):
        self.col.query.return_value = []
        with patch.object(db.utility, 'has_collection', return_value=True), patch.object(db, 'Collection', return_value=self.col):
            self.assertFalse(self.manager.delete_vector('agent_rag', '123'))
        self.col.delete.assert_not_called()

    def test_injection_and_unsafe_numeric_ids_are_rejected(self):
        for value in ['1 or pk > 0', '1.5', '9223372036854775808', 469553067275599162]:
            with self.assertRaises(ValueError):
                self.manager._primary_key_expression(self.primary, value)
        varchar = SimpleNamespace(name='id', dtype=DataType.VARCHAR)
        self.assertEqual(self.manager._primary_key_expression(varchar, 'a"b'), 'id == "a\\"b"')

    def test_routes_report_unavailable_bad_input_and_missing_record(self):
        app = Flask(__name__)
        app.register_blueprint(api.vector_bp)
        client = app.test_client()
        with patch.object(api, 'vector_manager', None):
            self.assertEqual(client.get('/api/vector/vectors?collection_name=agent_rag').status_code, 503)
        with patch.object(api, 'vector_manager', self.manager):
            self.assertEqual(client.get('/api/vector/vectors?collection_name=agent_rag&limit=abc').status_code, 400)
            self.assertEqual(client.get('/api/vector/vectors').status_code, 400)
        manager = MagicMock()
        manager.delete_vector.return_value = False
        with patch.object(api, 'vector_manager', manager):
            self.assertEqual(client.delete('/api/vector/vectors/123?collection_name=agent_rag').status_code, 404)
            manager.delete_vector.return_value = True
            response = client.delete('/api/vector/vectors/469553067275599162?collection_name=agent_rag')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json['id'], '469553067275599162')

    def test_collection_names_are_sorted(self):
        with patch.object(db.utility, 'list_collections', return_value=['bank_rag_v2', 'agent_rag']):
            self.assertEqual(self.manager.list_collections(), ['agent_rag', 'bank_rag_v2'])

    def test_batch_deletes_existing_ids_once_and_reports_missing(self):
        self.col.query.return_value = [{'pk': 469553067275599162}, {'pk': 469553067275599163}]
        with patch.object(db.utility, 'has_collection', return_value=True), patch.object(db, 'Collection', return_value=self.col):
            result = self.manager.delete_vectors('bank_rag_v2',
                ['469553067275599162', '469553067275599163', '999', '469553067275599162'])
        self.assertEqual(result['deleted_ids'], ['469553067275599162', '469553067275599163'])
        self.assertEqual(result['missing_ids'], ['999'])
        self.col.delete.assert_called_once_with(
            expr='pk in [469553067275599162, 469553067275599163]', timeout=15)
        self.assertEqual(self.col.query.call_args.kwargs['consistency_level'], 'Strong')

    def test_invalid_batch_is_rejected_before_any_mutation(self):
        with patch.object(db.utility, 'has_collection', return_value=True), patch.object(db, 'Collection', return_value=self.col):
            for values in [[], ['1', '1 or pk > 0'], ['1', '9223372036854775808'], [123], [''], ['1'] * 101, '123']:
                with self.subTest(values=values), self.assertRaises(ValueError):
                    self.manager.delete_vectors('agent_rag', values)
        self.col.query.assert_not_called()
        self.col.delete.assert_not_called()

    def test_batch_missing_records_do_not_delete(self):
        self.col.query.return_value = []
        with patch.object(db.utility, 'has_collection', return_value=True), patch.object(db, 'Collection', return_value=self.col):
            self.assertEqual(self.manager.delete_vectors('agent_rag', ['1']),
                             {'deleted_ids': [], 'missing_ids': ['1']})
        self.col.delete.assert_not_called()

    def test_batch_varchar_ids_are_escaped(self):
        self.primary.dtype = DataType.VARCHAR
        self.col.query.return_value = [{'pk': 'a"b'}]
        with patch.object(db.utility, 'has_collection', return_value=True), patch.object(db, 'Collection', return_value=self.col):
            self.manager.delete_vectors('agent_rag', ['a"b'])
        self.col.delete.assert_called_once_with(expr='pk in ["a\\"b"]', timeout=15)

    def test_collection_and_batch_routes(self):
        app = Flask(__name__)
        app.register_blueprint(api.vector_bp)
        client = app.test_client()
        with patch.object(api, 'vector_manager', None):
            self.assertEqual(client.get('/api/vector/collections').status_code, 503)
            self.assertEqual(client.post('/api/vector/vectors/batch_delete', json={}).status_code, 503)
        manager = MagicMock()
        manager.list_collections.return_value = ['agent_rag', 'bank_rag_v2']
        manager.delete_vectors.return_value = {'deleted_ids': ['469553067275599162'], 'missing_ids': []}
        with patch.object(api, 'vector_manager', manager):
            self.assertEqual(client.get('/api/vector/collections').json['collections'], ['agent_rag', 'bank_rag_v2'])
            self.assertEqual(client.post('/api/vector/vectors/batch_delete', json=[]).status_code, 400)
            payload = {'collection_name': 'agent_rag', 'vector_ids': ['469553067275599162']}
            response = client.post('/api/vector/vectors/batch_delete', json=payload)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json['deleted_ids'], payload['vector_ids'])
            manager.delete_vectors.assert_called_once_with('agent_rag', payload['vector_ids'])
            manager.delete_vectors.side_effect = ValueError('bad IDs')
            self.assertEqual(client.post('/api/vector/vectors/batch_delete', json=payload).status_code, 400)


if __name__ == '__main__':
    unittest.main()
