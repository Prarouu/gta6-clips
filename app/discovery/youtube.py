"""yt-dlp based YouTube search (no API key / quota needed). Metadata only - nothing is downloaded here.
Note: YouTube may block datacenter IPs (GitHub Actions) with a 'confirm you're not a bot' check. If that happens
the connector stops early and logs it; other sources continue."""
import time
from app.core.models import Candidate
from app.core.retry import retry

BOT_MARKERS = ("sign in to confirm", "not a bot", "http error 429", "too many requests")


def _is_blocked(e):
    return any(m in str(e).lower() for m in BOT_MARKERS)


def _cand_from_info(info, kw, connector="youtube_search"):
    vid = info.get("id")
    ts = info.get("timestamp")
    if not ts and info.get("upload_date"):
        import datetime as dt
        ts = dt.datetime.strptime(info["upload_date"], "%Y%m%d").replace(tzinfo=dt.timezone.utc).timestamp()
    url = info.get("webpage_url") or info.get("url") or f"https://www.youtube.com/watch?v={vid}"
    dur = info.get("duration")
    return Candidate(
        platform="youtube", source_id=vid, url=url, title=info.get("title") or "",
        creator=info.get("channel") or info.get("uploader") or "", creator_id=info.get("channel_id") or "",
        published_ts=ts, duration=dur, views=info.get("view_count"), likes=info.get("like_count"),
        comments=info.get("comment_count"), thumbnail=info.get("thumbnail") or "",
        description=info.get("description") or "", keyword=kw, connector=connector,
        is_short=("/shorts/" in url) or (dur is not None and dur <= 60) or None,
        downloadable=True, license=info.get("license") or "", height=info.get("height"),
        follower_count=info.get("channel_follower_count"))


def collect(ctx):
    try:
        import yt_dlp
    except ImportError as e:
        ctx.err("youtube_search", "import", e, source="youtube_search")
        return []
    cfg = ctx.settings["youtube"]
    retry_cfg = ctx.settings["retry"]
    base = {"quiet": True, "no_warnings": True, "skip_download": True, "socket_timeout": 20}
    flat, kw_of = {}, {}
    with yt_dlp.YoutubeDL({**base, "extract_flat": "in_playlist"}) as ydl:
        for kw in ctx.rotate(ctx.keywords["search_keywords"], cfg["ytdlp_keywords_per_run"]):
            q = f"ytsearchdate{cfg['ytdlp_results_per_keyword']}:{kw}"
            try:
                info = retry(lambda: ydl.extract_info(q, download=False), attempts=retry_cfg["attempts"],
                             base_delay=retry_cfg["base_delay_seconds"], label=f"ytdlp-search:{kw}")
            except Exception as e:
                ctx.err("youtube_search", "search", e, source=kw)
                if _is_blocked(e):
                    ctx.log.warning("youtube_search: YouTube is blocking this IP; stopping this connector early")
                    break
                continue
            for ent in (info or {}).get("entries", []) or []:
                if ent and ent.get("id") and ent["id"] not in flat:
                    flat[ent["id"]], kw_of[ent["id"]] = ent, kw
    out, enriched = [], 0
    order = sorted(flat.values(), key=lambda e: e.get("view_count") or 0, reverse=True)
    with yt_dlp.YoutubeDL(base) as ydl:
        for ent in order:
            vid = ent["id"]
            known = ctx.db.get_video("youtube", vid)
            if known and known["published_ts"]:
                c = _cand_from_info({**ent, "timestamp": known["published_ts"], "channel": known["creator_name"],
                                     "channel_id": known["creator_id"], "duration": known["duration"],
                                     "like_count": known["likes"], "comment_count": known["comments"],
                                     "thumbnail": known["thumbnail"], "description": known["description"]}, kw_of[vid])
                out.append(c)
                continue
            if enriched >= cfg["ytdlp_enrich_limit"]:
                continue
            try:
                info = retry(lambda: ydl.extract_info(f"https://www.youtube.com/watch?v={vid}", download=False),
                             attempts=2, base_delay=retry_cfg["base_delay_seconds"], label=f"ytdlp-info:{vid}")
                out.append(_cand_from_info(info, kw_of[vid]))
                enriched += 1
                time.sleep(0.5)
            except Exception as e:
                ctx.err("youtube_search", "enrich", e, video_id=vid, source="youtube_search")
                if _is_blocked(e):
                    break
    return out
