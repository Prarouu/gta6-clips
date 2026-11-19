"""Phase 2 daily scan: discover -> classify -> dedupe -> score -> select -> report. One failed source never stops the scan."""
import datetime as dt, importlib, logging, time
from app.core import config
from app.core.context import Ctx
from app.core.database import DB
from app.core.models import Candidate
from app.analysis import scoring, rights as rights_mod
from app.analysis.duplicate_detection import mark_duplicates
from app.reports.daily_report import write_reports

log = logging.getLogger("pipeline")
CONNECTORS = {
    "youtube_api": "app.discovery.youtube_api",
    "youtube_search": "app.discovery.youtube",
    "youtube_channels": "app.discovery.creators",
    "reddit": "app.discovery.reddit",
    "news_rss": "app.discovery.rss",
}
PROGRESSED = {"SELECTED", "DOWNLOADED", "PROCESSED", "APPROVED", "UPLOADED"}


def local_now(settings):
    try:
        from zoneinfo import ZoneInfo
        return dt.datetime.now(ZoneInfo(settings.get("timezone", "UTC")))
    except Exception:
        return dt.datetime.now(dt.timezone.utc)


def merge(cands):
    """Same video from several connectors -> one candidate; fill gaps, keep the richest metrics."""
    out = {}
    for c in cands:
        if not c.source_id:
            continue
        k = c.key
        if k not in out:
            out[k] = c
            continue
        a = out[k]
        for f in ("published_ts", "duration", "views", "likes", "comments", "height", "follower_count"):
            if getattr(a, f) is None and getattr(c, f) is not None:
                setattr(a, f, getattr(c, f))
        for f in ("thumbnail", "description", "license", "creator_id", "creator"):
            if not getattr(a, f) and getattr(c, f):
                setattr(a, f, getattr(c, f))
        a.is_official = a.is_official or c.is_official
        if c.connector == "youtube_api":   # API stats are the most complete/accurate
            for f in ("views", "likes", "comments"):
                if getattr(c, f) is not None:
                    setattr(a, f, getattr(c, f))
    return list(out.values())


def run_scan(collectors=None, settings=None, db=None, write=True):
    settings = settings or config.load_settings()
    keywords = config.load_keywords()
    db = db or DB()
    now = time.time()
    local = local_now(settings)
    scan_date = local.strftime("%Y-%m-%d")
    scan_id = db.start_scan(scan_date)
    ctx = Ctx(db=db, settings=settings, keywords=keywords, scan_id=scan_id, now_ts=now,
              api_key=config.youtube_api_key(), day_index=local.timetuple().tm_yday)
    db.sync_permissions(config.load_permissions())
    log.info("scan %s started (window=%sh, sources=%s)", scan_date, settings["window_hours"],
             [k for k, v in settings["enabled_sources"].items() if v])

    # ---- 1. discover (each source isolated)
    raw, per_source = [], {}
    for name, enabled in settings["enabled_sources"].items():
        if not enabled:
            continue
        try:
            fn = (collectors or {}).get(name) or importlib.import_module(CONNECTORS[name]).collect
            found = fn(ctx) or []
            per_source[name] = len(found)
            raw += found
            log.info("source=%s found=%d", name, len(found))
        except Exception as e:
            per_source[name] = 0
            ctx.err("pipeline", "collect", e, source=name)
    cands = merge(raw)

    # ---- 1b. top up channel-feed videos with API details when a key is available (1 unit per 50 videos)
    if ctx.api_key and settings["enabled_sources"].get("youtube_api"):
        need = [c for c in cands if c.platform == "youtube" and (c.duration is None or c.likes is None)]
        if need:
            try:
                from app.discovery import youtube_api
                extra = youtube_api.fetch_details(ctx, [c.source_id for c in need])
                youtube_api.attach_subscribers(ctx, extra)
                cands = merge(cands + extra)
            except Exception as e:
                ctx.err("youtube_api", "enrich", e, source="youtube_api")

    # ---- 2. classify + rights, persist raw facts
    ids = {}
    for c in cands:
        c.content_type = scoring.classify(c.title, c.description)
        c.relevance = scoring.relevance_score(c.title, c.description, keywords)
        rights_mod.determine_rights(c, db)
        try:
            ids[c.key] = db.upsert_candidate(c)
            if c.platform == "youtube":
                db.upsert_creator("youtube", c.creator_id, c.creator, c.follower_count)
                if c.follower_count is None:
                    c.follower_count = db.creator_followers("youtube", c.creator_id)
        except Exception as e:
            ctx.err("database", "upsert", e, video_id=c.source_id, source=c.platform)
    today = scan_date
    window_s = settings["window_hours"] * 3600

    # ---- 3. rejection rules
    for c in cands:
        prev = db.previous_selection(ids[c.key]) if c.key in ids else None
        if c.key not in ids:
            c.status, c.reason = "REJECTED", "could not be stored"
        elif c.rights == "RESTRICTED":
            c.status, c.reason = "REJECTED", "rights status RESTRICTED"
        elif not c.published_ts:
            c.status, c.reason = "REJECTED", "publish date unknown (cannot verify freshness)"
        elif now - c.published_ts > window_s:
            c.status, c.reason = "REJECTED", f"older than {settings['window_hours']}h window"
        elif c.published_ts - now > 3600:
            c.status, c.reason = "REJECTED", "publish date in the future (bad metadata)"
        elif c.relevance < settings["min_relevance"]:
            c.status, c.reason = "REJECTED", f"low GTA 6 relevance ({c.relevance:.0f})"
        elif prev and prev != today:
            c.status, c.reason = "REJECTED", f"already selected on {prev}"

    # ---- 4. score everything (rejected items too, so the report can explain them)
    live = [c for c in cands if c.status != "REJECTED"] or cands
    df = scoring.topic_document_frequency(live)
    for c in cands:
        hist = db.creator_view_history(c.platform, c.creator_id, c.source_id) if c.creator_id else []
        scoring.score_candidate(c, settings, now, df, hist)
        rights_mod.apply_warnings(c, settings)
        if c.status == "DISCOVERED" and c.score < settings["min_score"]:
            c.status, c.reason = "REJECTED", f"score {c.score} below minimum {settings['min_score']}"

    # ---- 5. dedupe (best-ranked wins) and select
    ranked = sorted(cands, key=lambda c: c.score, reverse=True)
    dups = mark_duplicates(ranked)
    videos = [c for c in ranked if c.status == "DISCOVERED" and c.kind == "video" and c.downloadable is not False]
    selected = videos[: settings["daily_target_max"]]   # never padded with low-score items
    for c in selected:
        c.status, c.reason = "SELECTED", "top-ranked eligible video"
    for c in ranked:
        if c.status == "DISCOVERED" and c.kind == "video":
            c.status, c.reason = "REJECTED", f"outside top {settings['daily_target_max']}"
    leads = [c for c in ranked if c.status == "DISCOVERED" and c.kind in ("post", "article")][:10]
    for c in leads:
        c.status, c.reason = "LEAD", "story lead (post/article) - candidate for original commentary"
    for c in ranked:
        if c.status == "DISCOVERED":
            c.status, c.reason = "REJECTED", "outside top 10 story leads"

    # ---- 6. persist outcomes
    for c in ranked:
        vid = ids.get(c.key)
        if not vid:
            continue
        try:
            db.update_classification(vid, c)
            db.save_score(vid, scan_id, c)
            cur = db.conn.execute("SELECT status FROM discovered_videos WHERE id=?", (vid,)).fetchone()["status"]
            if c.status == "SELECTED":
                db.set_state(vid, "SELECTED", c.reason, selected_date=today)
            elif cur not in PROGRESSED:
                db.set_state(vid, c.status, c.reason)
        except Exception as e:
            ctx.err("database", "persist", e, video_id=c.source_id, source=c.platform)

    summary = {
        "scan_id": scan_id, "date": scan_date, "discovered": len(cands), "per_source": per_source,
        "rejected": len([c for c in ranked if c.status == "REJECTED"]), "duplicates": dups,
        "eligible": len(videos), "selected": len(selected), "leads": len(leads),
        "below_target": len(selected) < settings["daily_target_min"],
        "errors": db.conn.execute("SELECT COUNT(*) n FROM scan_errors WHERE scan_id=?", (scan_id,)).fetchone()["n"],
        "api_quota_used_today": db.get_setting("yt_quota_" + dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d"), 0),
    }
    status = "OK" if summary["errors"] == 0 else "OK_WITH_ERRORS"
    if not cands:
        status = "NO_DATA"
    db.finish_scan(scan_id, status, summary["discovered"], summary["rejected"], dups, summary["eligible"],
                   summary["selected"], str(per_source))
    if write:
        summary["report_dir"] = str(write_reports(summary, ranked, settings, db))
    log.info("scan done: %s", {k: v for k, v in summary.items() if k != "per_source"})
    return summary, ranked
