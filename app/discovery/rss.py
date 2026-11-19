"""Gaming news RSS. Articles are 'story leads' for commentary ideas, not downloadable clips."""
import calendar, re, requests
from app.core.models import Candidate
from app.core.retry import retry

UA = {"User-Agent": "Mozilla/5.0 (compatible; gta6-shorts-research/1.0)"}


def collect(ctx):
    import feedparser
    core = ctx.keywords["core_terms"] + ctx.keywords["secondary_terms"]
    out = []
    for feed in ctx.settings["news_feeds"]:
        try:
            r = retry(lambda: requests.get(feed["url"], headers=UA, timeout=20),
                      attempts=ctx.settings["retry"]["attempts"], base_delay=ctx.settings["retry"]["base_delay_seconds"],
                      exceptions=(requests.RequestException,), label=f"rss:{feed['name']}")
            r.raise_for_status()
            for e in feedparser.parse(r.content).entries:
                text = f"{e.get('title','')} {e.get('summary','')}".lower()
                if not any(k in text for k in core):
                    continue
                ts = calendar.timegm(e["published_parsed"]) if e.get("published_parsed") else None
                thumb = ""
                if e.get("media_thumbnail"):
                    thumb = e["media_thumbnail"][0].get("url", "")
                out.append(Candidate(
                    platform="news", source_id=e.get("id") or e.get("link", ""), url=e.get("link", ""),
                    title=e.get("title", ""), kind="article", creator=feed["name"], published_ts=ts, thumbnail=thumb,
                    description=re.sub(r"<[^>]+>", " ", e.get("summary", ""))[:1000], keyword="news feed",
                    connector="news_rss", downloadable=False))
        except Exception as ex:
            ctx.err("news_rss", "feed", ex, source=feed["name"])
    return out
