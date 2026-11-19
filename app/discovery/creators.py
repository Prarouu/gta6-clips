"""Monitor specific channels via YouTube's public RSS feed (no key, no quota)."""
import re, time, calendar, requests
from app.core.models import Candidate
from app.core.retry import retry

UA = {"User-Agent": "Mozilla/5.0 (compatible; gta6-shorts-research/1.0)"}


def resolve_handle(ctx, handle):
    key = f"handle_{handle.lower()}"
    cached = ctx.db.get_setting(key)
    if cached:
        return cached
    r = retry(lambda: requests.get(f"https://www.youtube.com/{handle}", headers=UA, timeout=20),
              attempts=2, exceptions=(requests.RequestException,), label=f"resolve:{handle}")
    m = re.search(r'"channelId":"(UC[\w-]{22})"', r.text) or re.search(r'channel/(UC[\w-]{22})', r.text)
    if not m:
        raise ValueError(f"could not resolve channel id for {handle}")
    ctx.db.set_setting(key, m.group(1))
    return m.group(1)


def collect(ctx):
    import feedparser
    from app.core.config import load_creators
    out = []
    for ch in load_creators():
        name = ch.get("name") or ch.get("handle") or ch.get("channel_id")
        try:
            cid = ch.get("channel_id") or resolve_handle(ctx, ch["handle"])
            r = retry(lambda: requests.get(f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}",
                                           headers=UA, timeout=20),
                      attempts=ctx.settings["retry"]["attempts"], base_delay=ctx.settings["retry"]["base_delay_seconds"],
                      exceptions=(requests.RequestException,), label=f"rss:{name}")
            r.raise_for_status()
            feed = feedparser.parse(r.content)
            for e in feed.entries:
                vid = e.get("yt_videoid") or e.get("id", "").split(":")[-1]
                ts = calendar.timegm(e.published_parsed) if e.get("published_parsed") else None
                stats = e.get("media_statistics", {}) or {}
                rating = e.get("media_starrating", {}) or {}
                out.append(Candidate(
                    platform="youtube", source_id=vid, url=f"https://www.youtube.com/watch?v={vid}",
                    title=e.get("title", ""), creator=e.get("author", name), creator_id=cid, published_ts=ts,
                    views=int(stats["views"]) if stats.get("views") else None,
                    likes=int(rating["count"]) if rating.get("count") else None,
                    thumbnail=(e.get("media_thumbnail") or [{}])[0].get("url", ""),
                    description=e.get("summary", ""), keyword="channel monitor", connector="youtube_channels",
                    is_official=bool(ch.get("official")), downloadable=True))
            time.sleep(0.5)
        except Exception as ex:
            ctx.err("youtube_channels", "feed", ex, source=name)
    return out
