"""Explicit public-topic search; never reads the private conversation store."""
import fcntl
import html
import os
import re
import threading
import time
import urllib.request
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlencode, urlsplit

from core.bottles import FIELDS


QUERIES = {
    'ml': ('cat:cs.LG', '机器学习 研究'),
    'gpu': ('(all:GPU OR all:CUDA OR all:"tensor core")', 'GPU CUDA 研究'),
    'database': ('cat:cs.DB', '数据库 检索 研究'),
    'graph': ('(all:"graph learning" OR all:"temporal graph")', '图学习 时序图'),
    'robotics': ('cat:cs.RO', '具身智能 机器人'),
    'vision': ('cat:cs.CV', '计算机视觉 研究'),
    'nlp': ('cat:cs.CL', '自然语言处理 大模型'),
    'math': ('(cat:math.* OR cat:stat.*)', '数学 统计 研究'),
    'bio': ('cat:q-bio.*', '生命科学 研究'),
    'physics': ('(cat:cond-mat.* OR cat:physics.*)', '物理 材料 研究'),
    'social': ('cat:cs.CY', '社会科学 研究'),
    'other': ('cat:cs.AI', '人工智能 研究'),
}
ATOM = {'a': 'http://www.w3.org/2005/Atom'}
PAPER_TERMS = dict(ml='machine learning', gpu='GPU', database='database', graph='graph learning',
                   robotics='robotics', vision='computer vision', nlp='natural language processing',
                   math='statistics', bio='biology', physics='physics', social='social science', other='artificial intelligence')


def safe_url(value, host=None):
    try:
        p = urlsplit(value)
        return (p.scheme == 'https' and bool(p.hostname) and not p.username and not p.password
                and p.port in (None, 443) and (not host or p.hostname == host)
                and not re.search(r'[\s\x00-\x1f\\]', value))
    except ValueError:
        return False


def text(value, limit=400):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]*>', '', value or ''))).strip()[:limit]


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch_feed(url):
    # Only fixed provider URLs reach this function; never follow article URLs or redirects.
    request = urllib.request.Request(url, headers={'User-Agent': 'Between/0.1 (local research discovery)'})
    with urllib.request.build_opener(NoRedirect).open(request, timeout=12) as response:
        data = response.read(1048577)
    if len(data) > 1048576:
        raise ValueError('Feed too large')
    data = data.decode('utf-8-sig')
    if re.search(r'<!DOCTYPE|<!ENTITY', data, re.I):
        raise ValueError('Invalid feed')
    return ET.fromstring(data)


class DiscoverySearch:
    def __init__(self, root=None):
        self.root = Path(root or Path.home() / '.local/share/agent-waiting-discovery')
        self.lock = threading.Lock()
        self.cache = {}

    @contextmanager
    def arxiv_slot(self):
        # Shared by local profiles: arXiv permits one connection and a three-second interval.
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.root.is_symlink() or self.root.stat().st_mode & 0o077:
            raise ValueError('Unsafe rate-limit directory')
        fd = os.open(self.root / 'arxiv.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'r+') as handle:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            last = float(handle.read(64) or '0')
            now = time.time()
            if now - last < 3:
                raise ValueError('Rate limited')
            handle.seek(0); handle.truncate(); handle.write(str(now)); handle.flush()
            yield

    def search(self, body):
        if set(body) != {'field', 'kind', 'keyword', 'days', 'consent'} or body['consent'] is not True:
            raise ValueError('请确认仅发送所选领域与关键词。')
        field, kind, keyword, days = (body[k] for k in ['field', 'kind', 'keyword', 'days'])
        if (not isinstance(field, str) or field not in QUERIES
                or not isinstance(kind, str) or kind not in {'paper', 'article', 'wechat'}
                or not isinstance(keyword, str) or len(keyword) > 80
                or re.search(r'[\x00-\x1f\x7f]', keyword)
                or type(days) is not int or days not in {7, 30, 90}):
            raise ValueError('请选择有效领域、内容类型、时间范围，关键词限 80 字。')
        keyword = keyword.strip()
        key = (field, kind, keyword, days)
        with self.lock:
            now = datetime.now(timezone.utc)
            cached = self.cache.get(key)
            if cached and time.time() - cached['fetched_at'] < 600:
                return dict(cached, cached=True)
            since = now - timedelta(days=days)
            paper_query, news_query = QUERIES[field]
            if keyword:
                terms = re.findall(r'[\w.+#/-]+', keyword, re.UNICODE)
                if not terms:
                    raise ValueError('关键词需要包含文字或数字。')
                paper_query += ' AND ' + ' AND '.join('all:"' + t + '"' for t in terms)
                news_query += ' ' + ' '.join(terms)
            paper_query += ' AND submittedDate:[' + since.strftime('%Y%m%d%H%M') + ' TO ' + now.strftime('%Y%m%d%H%M') + ']'
            if kind == 'paper':
                url = 'https://export.arxiv.org/api/query?' + urlencode(dict(search_query=paper_query, sortBy='submittedDate', sortOrder='descending', max_results=12))
                fallback = 'https://arxiv.org/search/?' + urlencode(dict(query=keyword or PAPER_TERMS[field], searchtype='all', order='-announced_date_first'))
            else:
                query = news_query + (' site:mp.weixin.qq.com' if kind == 'wechat' else '') + ' when:' + str(days) + 'd'
                url = 'https://news.google.com/rss/search?' + urlencode(dict(q=query, hl='zh-CN', gl='CN', ceid='CN:zh-Hans'))
                fallback = ('https://weixin.sogou.com/weixin?' + urlencode(dict(type=2, query=FIELDS[field] + ' ' + keyword)) if kind == 'wechat'
                            else 'https://news.google.com/search?' + urlencode(dict(q=query, hl='zh-CN')))
            result = dict(items=[], field=field, kind=kind, days=days, keyword=keyword,
                          source='arXiv' if kind == 'paper' else 'Google News 公开索引',
                          fetched_at=time.time(), cached=False, fallback=fallback, status='ok', omitted=0)
            try:
                if kind == 'paper':
                    with self.arxiv_slot():
                        root = fetch_feed(url)
                    entries = root.findall('a:entry', ATOM)
                    if root.tag != '{' + ATOM['a'] + '}feed' or any('/api/errors' in e.findtext('a:id', '', ATOM) for e in entries):
                        raise ValueError('Provider error')
                    for e in entries:
                        link = e.findtext('a:id', '', ATOM).replace('http://arxiv.org/', 'https://arxiv.org/')
                        if not safe_url(link, 'arxiv.org') or not urlsplit(link).path.startswith('/abs/'):
                            continue
                        result['items'].append(dict(title=text(e.findtext('a:title', '', ATOM), 250), url=link,
                            source='arXiv · 预印本', published=e.findtext('a:published', '', ATOM),
                            summary=text(e.findtext('a:summary', '', ATOM)), date_label='首次提交'))
                else:
                    root = fetch_feed(url)
                    if root.tag != 'rss' or root.find('channel') is None:
                        raise ValueError('Provider error')
                    for e in root.findall('channel/item'):
                        link, source = e.findtext('link', ''), e.find('source')
                        if not safe_url(link, 'news.google.com') or source is None:
                            continue
                        if kind == 'wechat' and not safe_url(source.get('url', ''), 'mp.weixin.qq.com'):
                            continue
                        result['items'].append(dict(title=text(e.findtext('title'), 250), url=link,
                            source=text(source.text, 80) or '公开索引', published=e.findtext('pubDate', ''),
                            summary='', date_label='索引标注发布日 · 未独立核实'))
                items = {}
                for item in result['items']:
                    try:
                        stamp = (datetime.fromisoformat(item['published'].replace('Z', '+00:00')) if kind == 'paper'
                                 else parsedate_to_datetime(item['published']))
                        if stamp.tzinfo is None or not since <= stamp <= now:
                            raise ValueError('Out of range')
                    except (ValueError, TypeError, OverflowError):
                        result['omitted'] += 1
                        continue
                    if not item['title']:
                        continue
                    item['published'] = stamp.astimezone(timezone.utc).isoformat()
                    previous = items.get(item['url'])
                    if not previous or previous['published'] < item['published']:
                        items[item['url']] = item
                result['items'] = sorted(items.values(), key=lambda e: e['published'], reverse=True)[:12]
                if not result['items']:
                    result['status'] = 'empty'
            except (OSError, ValueError, ET.ParseError):
                result['items'] = []; result['status'] = 'unavailable'
            if result['status'] != 'unavailable':
                if len(self.cache) >= 24:
                    self.cache.pop(next(iter(self.cache)))
                self.cache[key] = result
            return result
