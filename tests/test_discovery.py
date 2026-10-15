import json
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock
from urllib.parse import parse_qs, urlsplit
from xml.sax.saxutils import escape

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'demo'))
from core.discovery import DiscoverySearch, fetch_feed, NoRedirect, safe_url


def paper(title='Synthetic metadata', url='https://arxiv.org/abs/2610.00001', stamp=None):
    stamp = stamp or (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    return '<entry><id>' + escape(url) + '</id><title>' + escape(title) + '</title><published>' + stamp + '</published><summary>Test metadata only.</summary></entry>'


def atom(*entries):
    return ET.fromstring('<feed xmlns="http://www.w3.org/2005/Atom">' + ''.join(entries) + '</feed>')


def news(title='Synthetic article', stamp=None, source='https://example.invalid', link='https://news.google.com/rss/articles/test'):
    stamp = stamp or (datetime.now(timezone.utc) - timedelta(days=1)).strftime('%a, %d %b %Y %H:%M:%S GMT')
    return '<item><title>' + escape(title) + '</title><link>' + escape(link) + '</link><pubDate>' + stamp + '</pubDate><source url="' + escape(source) + '">Synthetic publisher</source></item>'


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.search = DiscoverySearch(Path(self.tmp.name) / 'rate')
        self.body = dict(field='gpu', kind='paper', keyword='', days=30, consent=True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_consent_shape_and_input_boundaries_never_connect(self):
        invalid = [dict(consent=False), dict(consent='yes'), dict(days=True), dict(days=365),
                   dict(field=[]), dict(kind='all'), dict(keyword='x' * 81), dict(keyword='a\nsecret'),
                   dict(keyword='!!!'), dict(source_path='private')]
        with patch('core.discovery.fetch_feed') as fetch:
            for changes in invalid:
                with self.subTest(changes=changes), self.assertRaises(ValueError):
                    self.search.search(dict(self.body, **changes))
            fetch.assert_not_called()

    def test_papers_date_bounds_dedup_and_safe_links(self):
        now = datetime.now(timezone.utc)
        feed = atom(paper('Older', stamp=(now-timedelta(days=3)).isoformat()),
                    paper('Newest', url='https://arxiv.org/abs/2610.00002'),
                    paper('Duplicate', stamp=(now-timedelta(days=2)).isoformat()), paper('Old', url='https://arxiv.org/abs/2501.00001', stamp=(now-timedelta(days=40)).isoformat()),
                    paper('Future', url='https://arxiv.org/abs/2710.00001', stamp=(now+timedelta(days=1)).isoformat()),
                    paper('Bad date', url='https://arxiv.org/abs/2610.00003', stamp='not a date'),
                    paper('Not a paper', url='https://evil.invalid/abs/2610.00001'))
        with patch('core.discovery.fetch_feed', return_value=feed) as fetch:
            result = self.search.search(self.body)
        self.assertEqual([r['title'] for r in result['items']], ['Newest', 'Duplicate'])
        self.assertEqual(result['omitted'], 3)
        self.assertEqual(result['items'][0]['date_label'], '首次提交')
        query = parse_qs(urlsplit(fetch.call_args.args[0]).query)
        self.assertIn('submittedDate:[', query['search_query'][0])
        self.assertEqual(query['sortBy'], ['submittedDate'])
        self.assertEqual(query['sortOrder'], ['descending'])

    def test_keywords_are_quoted_and_only_sent_to_fixed_provider(self):
        with patch('core.discovery.fetch_feed', return_value=atom()) as fetch:
            self.search.search(dict(self.body, keyword='CUDA OR site:evil.invalid'))
        url = urlsplit(fetch.call_args.args[0])
        self.assertEqual(url.hostname, 'export.arxiv.org')
        query = parse_qs(url.query)['search_query'][0]
        self.assertIn('all:"OR"', query)
        self.assertNotIn('site:evil.invalid', query)

    def test_cache_keeps_original_fetch_time_and_does_not_reconnect(self):
        with patch('core.discovery.fetch_feed', return_value=atom(paper())) as fetch:
            first = self.search.search(self.body)
            second = self.search.search(self.body)
        self.assertEqual(fetch.call_count, 1)
        self.assertFalse(first['cached']); self.assertTrue(second['cached'])
        self.assertEqual(first['fetched_at'], second['fetched_at'])
        self.assertNotIn('timeline', json.dumps(second))

    def test_rate_limit_is_shared_between_profiles_and_limits_connections(self):
        other = DiscoverySearch(self.search.root)
        with patch('core.discovery.fetch_feed', return_value=atom(paper())) as fetch:
            with self.search.arxiv_slot():
                self.assertEqual(other.search(self.body)['status'], 'unavailable')
            self.assertEqual(other.search(self.body)['status'], 'unavailable')
            fetch.assert_not_called()
        self.assertEqual(self.search.root.stat().st_mode & 0o777, 0o700)
        self.assertEqual((self.search.root/'arxiv.lock').stat().st_mode & 0o777, 0o600)

    def test_article_dates_sort_in_utc_and_no_html_is_required(self):
        # Relative dates avoid a frozen fixture becoming a false "latest" claim.
        now = datetime.now(timezone.utc)
        first = now-timedelta(days=1)
        second = first-timedelta(hours=1)
        feed = ET.fromstring('<rss><channel>' + news('Newer', first.strftime('%a, %d %b %Y %H:%M:%S GMT')) + news('Older', second.astimezone(timezone(timedelta(hours=8))).strftime('%a, %d %b %Y %H:%M:%S %z'), link='https://news.google.com/rss/articles/older') + '</channel></rss>')
        with patch('core.discovery.fetch_feed', return_value=feed) as fetch:
            result = self.search.search(dict(self.body, kind='article'))
        self.assertEqual([r['title'] for r in result['items']], ['Newer', 'Older'])
        self.assertIn('未独立核实', result['items'][0]['date_label'])
        self.assertEqual(urlsplit(fetch.call_args.args[0]).hostname, 'news.google.com')

    def test_wechat_never_substitutes_non_wechat_items_or_claims_latest(self):
        feed = ET.fromstring('<rss><channel>' + news('Other site') + news('WeChat', source='https://mp.weixin.qq.com', link='https://news.google.com/rss/articles/wechat') + '</channel></rss>')
        with patch('core.discovery.fetch_feed', return_value=feed) as fetch:
            result = self.search.search(dict(self.body, kind='wechat'))
        self.assertEqual([r['title'] for r in result['items']], ['WeChat'])
        self.assertIn('site:mp.weixin.qq.com', parse_qs(urlsplit(fetch.call_args.args[0]).query)['q'][0])
        self.assertEqual(urlsplit(result['fallback']).hostname, 'weixin.sogou.com')

    def test_empty_and_unavailable_are_distinct_and_failures_are_not_cached(self):
        with patch('core.discovery.fetch_feed', side_effect=OSError('private upstream detail')):
            failed = self.search.search(dict(self.body, kind='article'))
        self.assertEqual(failed['status'], 'unavailable')
        self.assertNotIn('private upstream detail', json.dumps(failed))
        with patch('core.discovery.fetch_feed', return_value=ET.fromstring('<rss><channel/></rss>')):
            empty = self.search.search(dict(self.body, kind='article'))
        self.assertEqual(empty['status'], 'empty')
        self.assertFalse(empty['cached'])

    def test_feed_errors_and_invalid_dates_do_not_become_real_results(self):
        for feed in [ET.fromstring('<html/>'), ET.fromstring('<rss><channel>'+news(stamp='bad')+'</channel></rss>')]:
            with patch('core.discovery.fetch_feed', return_value=feed):
                result = DiscoverySearch(self.search.root).search(dict(self.body, kind='article'))
            self.assertEqual(result['items'], [])
        with patch('core.discovery.fetch_feed', return_value=atom(paper(url='http://arxiv.org/api/errors#x'))):
            self.assertEqual(self.search.search(self.body)['status'], 'unavailable')

    def test_feed_size_xml_entities_and_redirects_are_rejected(self):
        opener = MagicMock()
        response = opener.open.return_value.__enter__.return_value
        for data in [b'x'*1048577, b'<!DOCTYPE feed [<!ENTITY a "b">]><feed/>',
                     '<!DOCTYPE feed [<!ENTITY a "b">]><feed/>'.encode('utf-16')]:
            response.read.return_value = data
            with patch('core.discovery.urllib.request.build_opener', return_value=opener), self.assertRaises(ValueError):
                fetch_feed('https://export.arxiv.org/api/query')
        self.assertIsNone(NoRedirect().redirect_request(None, None, 302, '', {}, 'https://evil.invalid'))
        for url in ['javascript:bad', 'https://user:secret@arxiv.org/abs/1', 'https://arxiv.org:8000/abs/1', 'https://arxiv.org\\@evil.invalid/']:
            self.assertFalse(safe_url(url, 'arxiv.org'))
