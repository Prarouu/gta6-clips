# GTA 6 Shorts Discovery Pipeline (cloud, free)

**Phase 2 status:** discovery -> duplicate detection -> explainable ranking -> daily report, running on GitHub Actions.
Downloads, video processing, dashboard and YouTube upload come in Phases 3-6. Nothing here uploads or downloads videos.

## What it does each day
1. Searches YouTube (yt-dlp search, plus the optional free YouTube API), monitors channels you list (RSS), Reddit RSS, and gaming-news RSS.
2. Merges duplicates, drops stale/irrelevant/already-selected items, scores 0-100 with a visible breakdown.
3. Selects up to 15 clips (never padded below the target with weak items) plus up to 10 "story leads" (posts/articles).
4. Saves `data/gta6.db` and reports in `data/reports/<date>/` (CSV, HTML, Markdown) back to the repo.

## One-time setup (no coding)
1. Create a free GitHub account, then **New repository** -> name `gta6-shorts-automation` -> **Private** -> Create.
2. Add the project files. Easiest: install **GitHub Desktop** (free), clone the repo, copy this folder's contents into it (include the hidden-looking `.github` folder), then Commit and Push.
   Alternative: on the repo page choose *Add file -> Upload files* and drag the whole contents in; confirm `.github/workflows/daily.yml` appears in the file list.
3. Repo **Settings -> Actions -> General -> Workflow permissions** -> select **Read and write permissions** -> Save.
4. (Optional) YouTube API key: Google Cloud Console -> new project -> enable *YouTube Data API v3* -> Credentials -> API key.
   In the repo: **Settings -> Secrets and variables -> Actions -> New repository secret**, name `YOUTUBE_API_KEY`. Never paste the key into a file.
5. **Actions tab -> Daily GTA 6 scan -> Run workflow.** Wait a few minutes, open the run, and read the summary at the bottom.
6. Open `data/reports/latest.md` in the repo, or download the `reports-and-logs` artifact and open `latest.html`.

It then runs automatically every day at 03:00 UTC (08:30 AM IST). Change the `cron` line in `.github/workflows/daily.yml` to change the time.

## Customising (edit files in `config/` on GitHub with the pencil icon)
- `keywords.json` - search keywords, core/secondary relevance terms. Add freely.
- `settings.json` - time window (`window_hours`: 24 / 72 / 168 / custom), daily target, minimum score, sources on/off, score weights.
- `creators.json` - channels to monitor (use `@handle` or a `UC...` channel id). Rockstar is pre-added.
- `permissions.json` - record rights you have **verified** (e.g. a creator who gave written permission).

## Rights policy (important)
Every item gets a rights status. Default is `UNKNOWN`/`PERMISSION_REQUIRED`. Only `ORIGINAL`, `LICENSED`, `CREATOR_PERMISSION`,
`PUBLIC_DOMAIN` can ever be auto-uploaded (see `auto_publish_rights`). Creative Commons clips are flagged but still need a manual check.
Leak/rumour items are labelled UNVERIFIED. Cropping or subtitles does not make someone else's clip safe to repost.

## Known limitations (be aware)
- **YouTube may block GitHub's servers** for yt-dlp ("confirm you're not a bot"). The connector then stops and logs it; the API key and
  channel-RSS connectors are unaffected, so keep at least one of them on. Not bypassed, by design.
- **Reddit often blocks datacenter IPs** (403/429). Logged, scan continues. RSS has no vote counts.
- **Engagement/creator-relative scores are estimates.** Missing signals show as `n/a` and are excluded, not invented. Subscriber-based
  expectation assumes a typical video reaches `typical_view_fraction` (5%) of subscribers - adjust in settings.
- **Google Trends is not included**; free access is unreliable. Topic frequency among the day's items is used for the trending signal.
- The free API quota is ~10,000 units/day; search costs 100. A self-imposed budget (`api_daily_budget_units`) protects it.
- Free-tier terms can change.

## Local test (optional)
`pip install -r requirements.txt`, then `python run.py check`, `python run.py demo` (offline sample data), `python -m unittest discover -s tests -t .`
