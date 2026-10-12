"""Request diagnostics and grounded answers; no live Milvus or paid LLM calls."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from langchain_core.documents import Document
from backend.app.vector_retriever import VectorRetriever


class RagTraceTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {'L2_MAX_DISTANCE': '0.5'})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.manager = MagicMock()
        self.retriever = VectorRetriever(self.manager)
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        # Exercise the real atomic writer in a temporary project directory.
        self.fake_module = Path(self.directory.name) / 'backend' / 'app' / 'vector_retriever.py'
        self.module_path = patch('backend.app.vector_retriever.__file__', str(self.fake_module))
        self.module_path.start()
        self.addCleanup(self.module_path.stop)

    def read_trace(self, result):
        path = Path(self.directory.name) / 'logs' / 'rag_traces' / f'{result.request_id}.json'
        return json.loads(path.read_text(encoding='utf-8'))

    def test_filtered_candidates_are_saved_without_calling_llm(self):
        self.manager.search.return_value = [(Document(page_content='测试制度', metadata={'source': '规则.txt'}), 8135.5)]
        with patch.object(self.retriever, '_generate_answer_with_llm') as generate:
            result = self.retriever.answer_question('营业机构何时停办业务', 'agent_rag')
        generate.assert_not_called()
        self.assertEqual(result.status, 'no_context')
        trace = self.read_trace(result)
        self.assertEqual(trace['candidates'][0]['distance'], 8135.5)
        self.assertFalse(trace['candidates'][0]['kept'])
        self.assertEqual(trace['candidates'][0]['content'], '测试制度')
        self.assertFalse(trace['llm_called'])
        self.assertIsNone(trace['messages'])
        self.assertEqual(trace['answer'], result.answer)

    def test_actual_llm_messages_parameters_and_answer_are_saved(self):
        self.manager.search.return_value = [(Document(page_content='通常五个工作日完成初步审核', metadata={'source': '贷款.txt'}), 0.2)]
        client = MagicMock()
        client.chat.completions.create.return_value = SimpleNamespace(
            model='test-model', choices=[SimpleNamespace(message=SimpleNamespace(content='不是保证审批通过。'), finish_reason='stop')])
        with patch('openai.OpenAI', return_value=client):
            result = self.retriever.answer_question('一定审批通过吗？', 'agent_rag')
        trace = self.read_trace(result)
        call = client.chat.completions.create.call_args.kwargs
        self.assertEqual(trace['messages'], call['messages'])
        self.assertEqual(trace['generation_params']['temperature'], call['temperature'])
        self.assertIn('贷款.txt', trace['context'])
        self.assertEqual(trace['answer'], '不是保证审批通过。')
        self.assertEqual(trace['status'], 'answered')
        self.assertNotIn('api_key', trace)

    def test_retrieval_error_is_distinct_from_no_context(self):
        self.manager.search.side_effect = RuntimeError('offline')
        result = self.retriever.answer_question('问题', 'agent_rag')
        trace = self.read_trace(result)
        self.assertEqual(result.status, 'error')
        self.assertEqual(trace['error']['stage'], 'retrieval')
        self.assertFalse(trace['llm_called'])

    def test_generation_failure_preserves_messages_and_candidates(self):
        self.manager.search.return_value = [(Document(page_content='依据'), 0.2)]
        client = MagicMock()
        client.chat.completions.create.side_effect = RuntimeError('offline')
        with patch('openai.OpenAI', return_value=client):
            result = self.retriever.answer_question('问题', 'agent_rag')
        trace = self.read_trace(result)
        self.assertEqual(result.status, 'error')
        self.assertEqual(trace['error']['stage'], 'generation')
        self.assertEqual(len(trace['messages']), 2)
        self.assertEqual(len(trace['candidates']), 1)

    def test_request_files_are_separate(self):
        self.manager.search.return_value = []
        first = self.retriever.answer_question('问题一', 'agent_rag')
        second = self.retriever.answer_question('问题二', 'agent_rag')
        self.assertNotEqual(first.request_id, second.request_id)
        self.assertEqual(self.read_trace(first)['question'], '问题一')
        self.assertEqual(self.read_trace(second)['question'], '问题二')

    def test_default_14000_includes_boundary_and_rejects_larger_distance(self):
        with patch.dict(os.environ):
            os.environ.pop('L2_MAX_DISTANCE', None)
            retriever = VectorRetriever(self.manager)
        self.assertEqual(retriever.similarity_threshold, 14000.0)
        self.manager.search.return_value = [
            (Document(page_content='低于阈值'), 13999.0),
            (Document(page_content='等于阈值'), 14000.0),
            (Document(page_content='超过阈值'), 14001.0),
        ]
        with patch.object(retriever, '_generate_answer_with_llm', return_value='有依据的回答'):
            result = retriever.answer_question('问题', 'agent_rag')
        self.assertEqual(result.scores, [13999.0, 14000.0])
        self.assertEqual([row['kept'] for row in self.read_trace(result)['candidates']], [True, True, False])


if __name__ == '__main__':
    unittest.main()
