import csv, datetime as dt, html, shutil
from app.core.config import REPORT_DIR


def _fmt_date(ts):
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC") if ts else "unknown"


def _n(v):
    return "n/a" if v is None else f"{v:,}"


def write_reports(summary, ranked, settings, db):
    out = REPORT_DIR / summary["date"]
    out.mkdir(parents=True, exist_ok=True)
    comps = list(settings["score_weights"].keys())
    with open(out / "daily_report.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["rank", "status", "reason", "score", "platform", "type", "title", "creator", "views", "likes",
                    "comments", "published", "duration_s", "rights", "url", "warnings"] + [f"c_{k}" for k in comps])
        for i, c in enumerate(ranked, 1):
            w.writerow([i, c.status, c.reason, c.score, c.platform, c.content_type, c.title, c.creator,
                        c.views if c.views is not None else "", c.likes if c.likes is not None else "",
                        c.comments if c.comments is not None else "", _fmt_date(c.published_ts),
                        c.duration or "", c.rights, c.url, " | ".join(c.warnings)] +
                       [(c.components.get(k, {}).get("score")) if c.components.get(k, {}).get("score") is not None else "n/a" for k in comps])

    def card(i, c):
        rows = "".join(
            f"<tr><td>{html.escape(k)}</td><td>{'n/a' if v['score'] is None else v['score']}</td><td>{v['weight']}</td>"
            f"<td>{html.escape(v['note'])}</td></tr>" for k, v in c.components.items())
        warn = "".join(f"<div class='warn'>{html.escape(x)}</div>" for x in c.warnings)
        th = f"<img src='{html.escape(c.thumbnail)}' loading='lazy'>" if c.thumbnail else ""
        return (f"<div class='card'>{th}<div class='body'><h3>{i}. {html.escape(c.title)}</h3>"
                f"<div class='meta'><b>Score {c.score}</b> &middot; {html.escape(c.platform)} &middot; {html.escape(c.creator)} &middot; "
                f"{html.escape(c.content_type)} &middot; views {_n(c.views)} &middot; {_fmt_date(c.published_ts)} &middot; "
                f"rights <b>{html.escape(c.rights)}</b></div>{warn}"
                f"<div class='why'>{html.escape(c.explanation)}</div>"
                f"<a href='{html.escape(c.url)}' target='_blank' rel='noopener'>Open source</a>"
                f"<details><summary>Score components</summary><table><tr><th>Component</th><th>Score</th><th>Weight</th><th>Note</th></tr>{rows}</table></details>"
                f"</div></div>")

    sel = [c for c in ranked if c.status == "SELECTED"]
    leads = [c for c in ranked if c.status == "LEAD"]
    rej = [c for c in ranked if c.status in ("REJECTED", "DUPLICATE")]
    reasons = {}
    for c in rej:
        key = c.reason.split(":")[0] if c.status == "DUPLICATE" else c.reason.split("(")[0].strip()
        reasons[key] = reasons.get(key, 0) + 1
    src = ", ".join(f"{k}: {v}" for k, v in summary["per_source"].items())
    note = ""
    if summary["below_target"]:
        note = (f"<p class='warn'>Only {summary['selected']} eligible clips today (target {settings['daily_target_min']}-"
                f"{settings['daily_target_max']}). The list was NOT padded with low-quality items.</p>")
    page = f"""<!doctype html><html><head><meta charset='utf-8'><title>GTA 6 daily report {summary['date']}</title>
<style>body{{font-family:Arial,sans-serif;max-width:1000px;margin:24px auto;padding:0 12px;color:#1b1b1b}}
.card{{display:flex;gap:14px;border:1px solid #ddd;border-radius:8px;padding:12px;margin:12px 0}}
.card img{{width:200px;height:112px;object-fit:cover;border-radius:6px}} .body{{flex:1}} h3{{margin:0 0 6px}}
.meta,.why{{font-size:13px;color:#444;margin:4px 0}} .warn{{background:#fff3cd;border-left:4px solid #e0a800;padding:6px 8px;margin:6px 0;font-size:13px}}
table{{border-collapse:collapse;font-size:12px;margin-top:6px}} td,th{{border:1px solid #ddd;padding:4px 6px;text-align:left}}
.stats span{{display:inline-block;background:#eef2ff;border-radius:6px;padding:6px 10px;margin:3px}}</style></head><body>
<h1>GTA 6 daily report &ndash; {summary['date']}</h1>
<div class='stats'><span>Discovered <b>{summary['discovered']}</b></span><span>Rejected <b>{summary['rejected']}</b></span>
<span>Duplicates <b>{summary['duplicates']}</b></span><span>Eligible videos <b>{summary['eligible']}</b></span>
<span>Selected <b>{summary['selected']}</b></span><span>Story leads <b>{summary['leads']}</b></span>
<span>Errors <b>{summary['errors']}</b></span></div>
<p>Per source: {html.escape(src)}</p>{note}
<p class='meta'>Scores are explainable ESTIMATES. Signals that could not be measured are shown as n/a and excluded, never invented.
Rights: only verified permission/licence statuses are eligible for automatic upload; everything else is review-only.</p>
<h2>Top clips ({len(sel)})</h2>{''.join(card(i, c) for i, c in enumerate(sel, 1)) or '<p>None today.</p>'}
<h2>Story leads &ndash; posts &amp; news ({len(leads)})</h2>{''.join(card(i, c) for i, c in enumerate(leads, 1)) or '<p>None today.</p>'}
<h2>Why items were rejected</h2><table><tr><th>Reason</th><th>Count</th></tr>
{''.join(f"<tr><td>{html.escape(k)}</td><td>{v}</td></tr>" for k, v in sorted(reasons.items(), key=lambda x: -x[1]))}</table>
<p>Full detail for every item: daily_report.csv</p></body></html>"""
    (out / "daily_report.html").write_text(page, encoding="utf-8")

    md = [f"## GTA 6 daily report {summary['date']}",
          f"Discovered **{summary['discovered']}** | rejected {summary['rejected']} | duplicates {summary['duplicates']} | "
          f"eligible {summary['eligible']} | selected **{summary['selected']}** | leads {summary['leads']} | errors {summary['errors']}",
          f"Per source: {src}", ""]
    if summary["below_target"]:
        md.append(f"> Only {summary['selected']} eligible clips (target {settings['daily_target_min']}+). Not padded.\n")
    md += ["| # | Score | Title | Creator | Views | Rights |", "|---|---|---|---|---|---|"]
    for i, c in enumerate(sel, 1):
        md.append(f"| {i} | {c.score} | [{c.title.replace('|', ' ')[:80]}]({c.url}) | {c.creator} | {_n(c.views)} | {c.rights} |")
    (out / "daily_report.md").write_text("\n".join(md), encoding="utf-8")
    for name in ("daily_report.html", "daily_report.csv", "daily_report.md"):
        shutil.copyfile(out / name, REPORT_DIR / name.replace("daily_report", "latest"))
    return out
