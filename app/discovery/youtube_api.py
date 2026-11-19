"""YouTube Data API v3 (optional, free quota). search.list = 100 units, videos.list/channels.list = 1 unit.
A self-imposed daily budget protects the 10,000-unit default quota."""
import datetime as dt, re, requests
from app.core.models import Candidate
from app.core.retry import retry

BASE = "https://www.googleapis.com/youtube/v3"


class QuotaExceeded(Exception):
    pass


def _iso_duration(s):
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", s or "")
    if not m:
        return None
    d, h, mi, sec = (int(x or 0) for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + sec


def _get(ctx, path, params, cost):
    day = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    key = f"yt_quota_{day}"
    used = int(ctx.db.get_setting(key, 0))
    if used + cost > ctx.settings["youtube"]["api_daily_budget_units"]:
        raise QuotaExceeded(f"self-imposed daily budget reached ({used} units)")
    r = retry(lambda: requests.get(f"{BASE}/{path}", params={**params, "key": ctx.api_key}, timeout=20),
              attempts=ctx.settings["retry"]["attempts"], base_delay=ctx.settings["retry"]["base_delay_seconds"],
              exceptions=(requests.RequestException,), label=f"yt-api-{path}")
    if r.status_code == 403 and "quota" in r.text.lower():
        raise QuotaExceeded("YouTube reported quotaExceeded")
    r.raise_for_status()
    ctx.db.set_setting(key, used + cost)
    return r.json()


def _to_candidate(item, kw=""):
    sn, st, cd = item.get("snippet", {}), item.get("statistics", {}), item.get("contentDetails", {})
    vid = item["id"]
    pub = dt.datetime.fromisoformat(sn["publishedAt"].replace("Z", "+00:00")).timestamp() if sn.get("publishedAt") else None
    dur = _iso_duration(cd.get("duration"))
    th = sn.get("thumbnails", {})
    thumb = (th.get("high") or th.get("medium") or th.get("default") or {}).get("url", "")
    lic = item.get("status", {}).get("license", "")
    return Candidate(
        platform="youtube", source_id=vid, url=f"https://www.youtube.com/watch?v={vid}", title=sn.get("title", ""),
        creator=sn.get("channelTitle", ""), creator_id=sn.get("channelId", ""), published_ts=pub, duration=dur,
        views=int(st["viewCount"]) if "viewCount" in st else None,
        likes=int(st["likeCount"]) if "likeCount" in st else None,
        comments=int(st["commentCount"]) if "commentCount" in st else None,
        thumbnail=thumb, description=sn.get("description", ""), keyword=kw, connector="youtube_api",
        is_short=(dur is not None and dur <= 60) or None, downloadable=True,
        license="Creative Commons" if lic == "creativeCommon" else "")


def fetch_details(ctx, ids, kw_map=None):
    out = []
    ids = list(ids)
    for i in range(0, len(ids), 50):
        chunk = ids[i:i + 50]
        data = _get(ctx, "videos", {"part": "snippet,statistics,contentDetails,status", "id": ",".join(chunk)}, 1)
        out += [_to_candidate(it, (kw_map or {}).get(it["id"], "")) for it in data.get("items", [])]
    return out


def attach_subscribers(ctx, cands):
    ids = sorted({c.creator_id for c in cands if c.creator_id and c.follower_count is None})
    for i in range(0, len(ids), 50):
        data = _get(ctx, "channels", {"part": "statistics", "id": ",".join(ids[i:i + 50])}, 1)
        subs = {it["id"]: it["statistics"].get("subscriberCount") for it in data.get("items", [])
                if not it["statistics"].get("hiddenSubscriberCount")}
        for c in cands:
            if c.creator_id in subs and subs[c.creator_id]:
                c.follower_count = int(subs[c.creator_id])


def collect(ctx):
    if not ctx.api_key:
        ctx.log.info("youtube_api: no YOUTUBE_API_KEY set - skipping (yt-dlp search still runs)")
        return []
    cfg = ctx.settings["youtube"]
    after = dt.datetime.fromtimestamp(ctx.now_ts - ctx.settings["window_hours"] * 3600, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    kw_map = {}
    try:
        for kw in ctx.rotate(ctx.keywords["search_keywords"], cfg["api_keywords_per_run"]):
            data = _get(ctx, "search", {"part": "snippet", "q": kw, "type": "video", "order": "date",
                                        "publishedAfter": after, "maxResults": cfg["api_results_per_keyword"]}, 100)
            for it in data.get("items", []):
                kw_map.setdefault(it["id"]["videoId"], kw)
        cands = fetch_details(ctx, kw_map.keys(), kw_map)
        attach_subscribers(ctx, cands)
        return cands
    except QuotaExceeded as e:
        ctx.err("youtube_api", "quota", e, source="youtube_api")
        # keep whatever was found before the quota ran out
        return fetch_details(ctx, kw_map.keys(), kw_map) if kw_map else []
