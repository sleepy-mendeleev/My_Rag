"""Upload isolation and error reporting without real embedding or database writes."""
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from flask import Flask
from backend.app import api_integration as api


class UploadFileTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(api.vector_bp)
        self.client = self.app.test_client()
        self.manager = MagicMock()
        self.manager.process_file.return_value = True
        self.manager.get_database_info.return_value = {'document_count': 1}
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        for item in [patch.object(api, 'vector_manager', self.manager),
                     patch.object(api, 'UPLOAD_FOLDER', self.directory.name)]:
            item.start()
            self.addCleanup(item.stop)

    def upload(self, name, body=b'test'):
        return self.client.post('/api/vector/upload_file', data={
            'collection_name': 'bank_rag_v2', 'file': (io.BytesIO(body), name)})

    def test_same_name_uploads_keep_separate_contents(self):
        self.assertEqual(self.upload('same.txt', b'first').status_code, 200)
        self.assertEqual(self.upload('same.txt', b'second').status_code, 200)
        paths = [Path(call.args[0]) for call in self.manager.process_file.call_args_list]
        self.assertNotEqual(paths[0], paths[1])
        self.assertEqual([path.read_bytes() for path in paths], [b'first', b'second'])

    def test_chinese_filename_keeps_extension_and_original_label(self):
        response = self.upload('银行制度.pdf')
        self.assertEqual(response.status_code, 200)
        call = self.manager.process_file.call_args
        self.assertEqual(Path(call.args[0]).suffix, '.pdf')
        self.assertEqual(call.kwargs['file_name'], '银行制度.pdf')

    def test_unsupported_file_does_not_start_ingestion(self):
        self.assertEqual(self.upload('unsupported.exe').status_code, 400)
        self.manager.process_file.assert_not_called()

    def test_failed_file_does_not_block_next_request(self):
        self.manager.process_file.side_effect = [ValueError('OCR required'), True]
        first = self.upload('scan.pdf')
        second = self.upload('rules.txt')
        self.assertEqual(first.status_code, 400)
        self.assertEqual(first.json['message'], 'OCR required')
        self.assertEqual(second.status_code, 200)


if __name__ == '__main__':
    unittest.main()
