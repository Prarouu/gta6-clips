"""Reddit public RSS feeds (no login/API key). Reddit often blocks datacenter IPs (HTTP 403/429); when that happens
the error is logged and the scan continues. RSS exposes no vote counts, so Reddit items have no engagement metrics."""
import calendar, re, time, urllib.parse, requests
from app.core.models import Candidate
from app.core.retry import retry

UA = {"User-Agent": "gta6-shorts-research/1.0 (personal research script)"}


def _fetch(ctx, url, label):
    def go():
        r = requests.get(url, headers=UA, timeout=20)
        if r.status_code in (429, 500, 502, 503):
            raise requests.RequestException(f"HTTP {r.status_code}")
        return r
    return retry(go, attempts=ctx.settings["retry"]["attempts"], base_delay=ctx.settings["retry"]["base_delay_seconds"],
                 exceptions=(requests.RequestException,), label=label)


def collect(ctx):
    import feedparser
    cfg = ctx.settings["reddit"]
    urls = [(f"https://www.reddit.com/r/{s}/new/.rss", f"r/{s}") for s in cfg["subreddits"]]
    for kw in ctx.rotate(ctx.keywords["search_keywords"], cfg["search_keywords_per_run"]):
        urls.append((f"https://www.reddit.com/search.rss?q={urllib.parse.quote(kw)}&sort=new&t=week", kw))
    out, seen = [], set()
    for url, label in urls:
        try:
            r = _fetch(ctx, url, f"reddit:{label}")
            if r.status_code != 200:
                raise RuntimeError(f"HTTP {r.status_code} (Reddit may be blocking this IP)")
            for e in feedparser.parse(r.content).entries:
                m = re.search(r"/comments/(\w+)/", e.get("link", ""))
                pid = m.group(1) if m else e.get("id", "")
                if not pid or pid in seen:
                    continue
                seen.add(pid)
                ts = calendar.timegm(e.published_parsed) if e.get("published_parsed") else (
                    calendar.timegm(e.updated_parsed) if e.get("updated_parsed") else None)
                thumb = ""
                mt = re.search(r'<img src="([^"]+)"', e.get("summary", "") or e.get("content", [{}])[0].get("value", ""))
                if mt:
                    thumb = mt.group(1)
                out.append(Candidate(
                    platform="reddit", source_id=pid, url=e.get("link", ""), title=e.get("title", ""), kind="post",
                    creator=(e.get("author") or "").replace("/u/", ""), published_ts=ts, thumbnail=thumb,
                    description=re.sub(r"<[^>]+>", " ", e.get("summary", ""))[:1000], keyword=label,
                    connector="reddit", downloadable=False))
            time.sleep(1.5)
        except Exception as ex:
            ctx.err("reddit", "feed", ex, source=label)
    return out
