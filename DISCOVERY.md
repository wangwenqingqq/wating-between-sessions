# Discovery: explicit public-topic search

In **Discovery / 再发现**, select a field, content type, optional keyword and a
7/30/90-day window, then click **搜索**. Opening the page or selecting controls
does not initiate an external request. Fields are a public catalog, not inferred
from conversations or copied from a participant's bottle profile.

| Type | Source | Date meaning | Coverage boundary |
| --- | --- | --- | --- |
| Papers | arXiv Atom API | First submission, sorted newest first | arXiv preprints, not all journals or a quality ranking |
| Articles | Google News RSS search | Index-supplied publication date, not independently verified | Publicly indexed news/articles, not all technical blogs |
| WeChat | Google News RSS restricted to `mp.weixin.qq.com` | Same index-date caveat | Sparse public index; a visible Sogou WeChat search link remains available |

The app filters dates to the selected window and excludes missing, invalid and
future dates; the UI reports omitted-date counts. An empty index is not evidence
that no relevant content exists. Provider failure is distinct from no matches.
The fallback links are external searches, not fetched or verified article cards;
the Sogou fallback's dates must be checked by the reader. No login scraping,
CAPTCHA solving, access-control bypass, or full-text redistribution is attempted.
Results carry source links and retrieval time, not generated recommendations.

Historical unresolved excerpts remain under **本机历史留白**, separate from new
external content. They still require the existing history-analysis consent and
can be filtered by their original category. The Timeline month filter does not
silently constrain the external search or this all-month historical view.

## Privacy and network boundary

- Authenticated `GET /api/discovery/fields` returns only the local catalog.
- Authenticated `POST /api/discovery/search` accepts exactly `field`, `kind`,
  `keyword` (at most 80 characters), `days`, and explicit `consent: true`.
- Only the corresponding public query is sent to the selected provider. No
  conversation, source path, project name, history excerpt, bottle profile,
  access key, or participant identifier is attached. Do not enter secrets or
  unpublished findings as public search keywords. Providers also see normal
  network metadata such as the requesting IP.
- The server never reads the private Store for search, follows provider
  redirects, fetches arbitrary user URLs, downloads article bodies, or logs
  keywords. Returned metadata renders as text; links use a new tab and suppress
  referrers. Normal user-clicked source links can redirect on the provider site.
- Results live in a bounded 24-query, ten-minute process-memory cache, with their
  original retrieval time shown on cache hits. No search history is persisted.
  A private `arxiv.lock` under the standard local discovery data directory stores
  only the most recent request timestamp. Local companion profiles share the
  same cross-process lock and three-second request interval.
- Fetches have a 12-second socket timeout, a 1 MiB response cap, and reject XML
  entity/DOCTYPE declarations. There is no new listener or public deployment.

The paper adapter follows the [arXiv API manual](https://info.arxiv.org/help/api/user-manual.html)
and [API rate limits](https://info.arxiv.org/help/api/tou.html). Google News RSS is
a best-effort public feed, not a contracted API or completeness/availability SLA.
Direct [Sogou WeChat search](https://weixin.sogou.com/) remains an explicit user
action; it is not claimed to guarantee recent results. Bing web RSS was rejected
after a live probe ignored the site restriction and returned unrelated domains.

## Checks

```sh
python3 -m unittest discover -s tests -v
node --test tests/test_ui.cjs
```

Offline tests use synthetic metadata and mocked providers. Live checks establish
one local query's connectivity and rendering, not relevance accuracy, exhaustive
literature coverage, publication correctness, or community demand.
