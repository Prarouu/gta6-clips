"""Explainable 0-100 ranking. Components with no reliable data are marked unavailable (score=None) and the
remaining weights are renormalised, so we never invent metrics. Output is flagged as an ESTIMATE."""
import math, re, statistics

STOP = set("the a an and or of to in on for with is are was were be this that it its at by from as you your "
           "i we they he she new video official full gta 6 vi grand theft auto vs how what why".split())
HOOK = ["leak", "leaked", "revealed", "finally", "insane", "hidden", "secret", "confirmed", "breaking",
        "first look", "new", "details", "everything", "you missed", "?", "vs", "reaction", "funny", "crazy"]
TYPE_RULES = [
    ("leak_rumor", ["leak", "leaked", "rumor", "rumour", "insider", "reportedly", "allegedly"]),
    ("trailer", ["trailer"]),
    ("news", ["news", "announce", "release date", "delay", "update", "confirmed", "report"]),
    ("funny", ["funny", "meme", "fail", "lol", "hilarious"]),
    ("reaction", ["reaction", "reacts", "reacting"]),
    ("tutorial", ["how to", "guide", "tutorial", "tips"]),
    ("comparison", [" vs ", "comparison", "compared", "versus"]),
    ("theory", ["theory", "theories", "explained", "breakdown", "analysis"]),
    ("facts", ["facts", "hidden detail", "details", "things you"]),
    ("gameplay", ["gameplay", "mission", "map", "vehicle", "character", "lucia", "jason"]),
]


def clamp(x, lo=0.0, hi=100.0):
    return max(lo, min(hi, x))


def tokens(text: str):
    return [t for t in re.findall(r"[a-z0-9]+", (text or "").lower()) if t not in STOP and len(t) > 2]


def relevance_score(title, description, kw_cfg) -> float:
    t, d = (title or "").lower(), (description or "").lower()
    core, sec = kw_cfg.get("core_terms", []), kw_cfg.get("secondary_terms", [])
    if any(k in t for k in core):
        return 100.0
    if any(k in d for k in core):
        return 70.0
    if any(k in t for k in sec):
        return 55.0   # e.g. "Rockstar" or "Lucia" alone - plausible but loosely related
    if any(k in d for k in sec):
        return 30.0
    return 0.0


def classify(title, description="") -> str:
    t = f" {(title or '').lower()} "
    for name, words in TYPE_RULES:
        if any(w in t for w in words):
            return name
    return "other"


def topic_document_frequency(cands):
    df = {}
    for c in cands:
        for tok in set(tokens(c.title)):
            df[tok] = df.get(tok, 0) + 1
    return df


def score_candidate(c, settings, now_ts, topic_df, view_history=None):
    w = settings["score_weights"]
    win_h = settings["window_hours"]
    comp = {}

    def put(name, score, note):
        comp[name] = {"score": None if score is None else round(clamp(score), 1), "weight": w.get(name, 0), "note": note}

    # A. engagement (velocity + like/comment ratios), only when metrics exist
    if c.views is not None and c.published_ts:
        age_days = max((now_ts - c.published_ts) / 86400, 0.25)
        vel = c.views / age_days
        parts, wts, notes = [25 * math.log10(vel + 1)], [0.6], [f"{vel:,.0f} views/day"]
        if c.likes is not None and c.views > 0:
            ratio = c.likes / c.views
            parts.append(ratio / 0.06 * 100); wts.append(0.25); notes.append(f"like ratio {ratio:.1%}")
        if c.comments is not None and c.views > 0:
            ratio = c.comments / c.views
            parts.append(ratio / 0.004 * 100); wts.append(0.15); notes.append(f"comment ratio {ratio:.2%}")
        put("engagement", sum(p * x for p, x in zip(parts, wts)) / sum(wts), ", ".join(notes))
    else:
        put("engagement", None, "views/date not available")

    # B. freshness
    if c.published_ts:
        age_h = max((now_ts - c.published_ts) / 3600, 0)
        put("freshness", 100 * math.exp(-age_h / (win_h / 2)), f"{age_h:.1f}h old (window {win_h}h)")
    else:
        put("freshness", None, "publish date unknown")

    # C. performance vs creator size (estimate)
    rel_score, rel_note = None, "no creator baseline available"
    hist = view_history or []
    if c.views is not None and c.kind == "video":
        if len(hist) >= 3:
            base = statistics.median(hist)
            basis = f"median of {len(hist)} earlier videos we saw from this creator ({base:,.0f})"
        elif c.follower_count:
            base = c.follower_count * settings["typical_view_fraction"]
            basis = (f"ESTIMATE: assumes a typical video reaches {settings['typical_view_fraction']:.0%} of "
                     f"{c.follower_count:,} subscribers")
        else:
            base = None
        if base and base > 0:
            ratio = max(c.views, 1) / base
            rel_score, rel_note = 50 + 50 * math.log10(ratio), f"{ratio:.1f}x expected; {basis}"
    put("relative_performance", rel_score, rel_note)

    # D. relevance
    put("relevance", c.relevance, f"keyword relevance {c.relevance:.0f}/100")

    # E. shorts suitability (videos only)
    if c.kind == "video" and c.duration:
        d = c.duration
        base = 100 if d <= 60 else 85 if d <= 90 else 60 if d <= 180 else 30 if d <= 600 else 10
        hooks = [h for h in HOOK if h in c.title.lower()]
        bonus = min(15, 5 * len(hooks))
        put("shorts_suitability", base + bonus, f"{d:.0f}s long" + (f", hook words: {', '.join(hooks)}" if hooks else ""))
    else:
        put("shorts_suitability", None, "duration unknown or not a video")

    # F. trending (topic frequency among today's candidates)
    toks = tokens(c.title)
    if toks and topic_df:
        top = sorted((topic_df.get(t, 1) for t in set(toks)), reverse=True)[:3]
        mx = max(topic_df.values())
        put("trending", 100 * (sum(top) / len(top)) / mx, "topic overlap with other items found today")
    else:
        put("trending", None, "not enough data")

    # H. quality (only what metadata can prove; no pixel analysis yet)
    if c.height:
        put("quality", 100 if c.height >= 1080 else 70 if c.height >= 720 else 40, f"{c.height}p source")
    else:
        put("quality", None, "resolution not measured (audio/visual analysis arrives in Phase 4)")

    avail = [(k, v) for k, v in comp.items() if v["score"] is not None]
    total_w = sum(v["weight"] for _, v in avail) or 1
    c.score = round(sum(v["score"] * v["weight"] for _, v in avail) / total_w, 1)
    completeness = total_w / (sum(w.values()) or 1)
    c.components = comp
    top3 = sorted(avail, key=lambda kv: kv[1]["score"] * kv[1]["weight"], reverse=True)[:3]
    c.explanation = (f"Score {c.score} (ESTIMATE, {completeness:.0%} of signals available). Strongest: " +
                     "; ".join(f"{k} {v['score']:.0f} ({v['note']})" for k, v in top3))
    missing = [k for k, v in comp.items() if v["score"] is None]
    if missing:
        c.explanation += f". Not measured: {', '.join(missing)}."
    return c
