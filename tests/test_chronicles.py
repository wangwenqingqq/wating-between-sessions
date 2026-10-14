import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'demo'))
from core.chronicles import event_topics, load_chronicles
from core.store import Store


class ChronicleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / 'data')
        self.store.set('history_enabled', True)

    def tearDown(self):
        self.temp.cleanup()

    def add_event(self, key, text, date='2026-10-12', kind='request', category='research', session='s'):
        event = dict(event_id=key, date=date, title=text[:64], summary=text, category=category, kind=kind,
                     source_session_id=session, source_provider='codex', source_path=str(Path(self.temp.name) / 'source.jsonl'),
                     source_line=1, source_hash=hashlib.sha256(text.encode()).hexdigest(), confidence=1.0)
        with self.store.connect() as db:
            db.execute('INSERT INTO timeline (' + ','.join(event) + ') VALUES (' + ','.join('?' for _ in event) + ')', list(event.values()))
        return event

    def test_named_topics_cross_references_and_unassigned_fallback(self):
        event = self.add_event('a', 'GTS 的 CUDA 查询实验')
        self.assertEqual(set(event_topics(event)), {'gts-tide', 'gpu-computing'})
        generic = self.add_event('b', '请继续', category='general')
        self.assertEqual(event_topics(generic), ['misc'])
        research = self.add_event('c', '研究选题的问题')
        self.assertEqual(event_topics(research), ['research-notes'])
        result = load_chronicles(self.store)
        self.assertEqual(result['stats']['events'], 3)
        self.assertEqual(sum(t['count'] for t in result['topics']), 4)
        self.assertIsNone(result['selected'])

    def test_dossier_contains_all_records_without_the_old_100_card_limit(self):
        for i in range(130):
            self.add_event(str(i), 'GTS 记录 ' + str(i), session='session-' + str(i % 13))
        result = load_chronicles(self.store, topic='gts-tide')
        self.assertEqual(result['stats']['events'], 130)
        self.assertEqual(result['selected']['count'], 130)
        self.assertEqual(result['selected']['sessions'], 13)
        self.assertEqual(len(result['selected']['events']), 130)
        self.assertIsNone(result['selected']['chapters']['decision'])
        self.assertIsNone(result['selected']['chapters']['reported_result'])

    def test_tool_transport_heading_is_not_a_topic(self):
        document = self.add_event('document', '课程合作合同.docx ## My request for Codex: 修改课程文稿', category='learning')
        self.assertNotIn('agent-workflow', event_topics(document))
        self.assertIn('writing-teaching', event_topics(document))
        self.assertIn('life-decisions', event_topics(document))
        self.assertEqual(event_topics(self.add_event('fund', '调研全球成长混合(QDII)A', category='general')), ['life-decisions'])
        self.assertIn('agent-workflow', event_topics(self.add_event('real', '## My request for Codex: 比较 Codex 工作流')))

    def test_chapters_are_exact_excerpts_and_chronology_is_ascending(self):
        reported = self.add_event('result', 'GTS 结果是助手自报的记录', '2026-10-12', 'reported_result')
        request = self.add_event('request', '研究 GTS 查询', '2026-08-01')
        pending = self.add_event('pending', 'GTS 还有待解决的问题', '2026-10-13', 'open_question')
        before = json.dumps(load_chronicles(self.store))
        topic = load_chronicles(self.store, topic='gts-tide')['selected']
        self.assertEqual([e['event_id'] for e in topic['events']], ['request', 'result', 'pending'])
        for kind, original in [('request', request), ('reported_result', reported), ('open_question', pending)]:
            for field in ['summary', 'source_session_id', 'source_path', 'source_line', 'source_hash']:
                self.assertEqual(topic['chapters'][kind][field], original[field])
        self.assertIsNone(topic['chapters']['decision'])
        self.assertEqual(json.dumps(load_chronicles(self.store)), before)

    def test_month_filter_and_empty_topic_do_not_invent_content(self):
        self.add_event('old', 'GTS 查询', '2026-08-01')
        self.add_event('new', 'TGN 实验', '2026-10-01')
        filtered = load_chronicles(self.store, month='2026-10', topic='gts-tide')
        self.assertEqual(filtered['stats']['events'], 1)
        self.assertEqual(filtered['selected']['events'], [])
        self.assertEqual(filtered['selected']['count'], 0)
        self.assertTrue(all(v is None for v in filtered['selected']['chapters'].values()))
        self.assertEqual(load_chronicles(self.store, month='2020-01')['topics'], [])
        with self.assertRaises(ValueError):
            load_chronicles(self.store, topic='nonexistent')

    def test_same_day_keeps_source_line_order_not_kind_or_hash_order(self):
        self.add_event('z', 'GTS 阶段自报', kind='reported_result')
        self.add_event('a', 'GTS 明确选择', kind='decision')
        self.add_event('b', 'GTS 更晚自报', kind='reported_result')
        with self.store.connect() as db:
            for key, line in [('z', 10), ('a', 30), ('b', 100)]:
                db.execute('UPDATE timeline SET source_line=? WHERE event_id=?', (line, key))
        topic = load_chronicles(self.store, topic='gts-tide')['selected']
        self.assertEqual([e['event_id'] for e in topic['events']], ['z', 'a', 'b'])
        self.assertEqual(topic['chapters']['reported_result']['event_id'], 'b')

    def test_disabled_history_never_returns_chapters_or_excerpts(self):
        self.add_event('private', 'GTS private fixture')
        self.store.set('history_enabled', False)
        result = load_chronicles(self.store, topic='gts-tide')
        self.assertEqual(result['stats']['events'], 0)
        self.assertEqual(result['topics'], [])
        self.assertEqual(result['selected']['events'], [])
        self.assertNotIn('private fixture', json.dumps(result))


if __name__ == '__main__':
    unittest.main()
