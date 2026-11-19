import json, sqlite3, time
from contextlib import contextmanager
from app.core.config import DB_PATH, DATA_DIR

SCHEMA = """
CREATE TABLE IF NOT EXISTS discovered_videos(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  platform TEXT NOT NULL, source_id TEXT NOT NULL, url TEXT NOT NULL, title TEXT, kind TEXT,
  creator_id TEXT, creator_name TEXT, published_ts REAL, duration REAL,
  views INTEGER, likes INTEGER, comments INTEGER, thumbnail TEXT, description TEXT,
  keyword TEXT, content_type TEXT, relevance REAL, is_short INTEGER, is_official INTEGER,
  downloadable INTEGER, license TEXT, rights_status TEXT DEFAULT 'UNKNOWN',
  first_seen REAL, last_seen REAL, times_seen INTEGER DEFAULT 1,
  status TEXT DEFAULT 'DISCOVERED', selected_date TEXT,
  UNIQUE(platform, source_id));
CREATE UNIQUE INDEX IF NOT EXISTS ux_dv_url ON discovered_videos(url);
CREATE TABLE IF NOT EXISTS creators(
  id INTEGER PRIMARY KEY AUTOINCREMENT, platform TEXT NOT NULL, channel_id TEXT NOT NULL,
  name TEXT, follower_count INTEGER, last_seen REAL, UNIQUE(platform, channel_id));
CREATE TABLE IF NOT EXISTS daily_scans(
  id INTEGER PRIMARY KEY AUTOINCREMENT, scan_date TEXT NOT NULL, started_at REAL, finished_at REAL,
  status TEXT, discovered INTEGER DEFAULT 0, rejected INTEGER DEFAULT 0, duplicates INTEGER DEFAULT 0,
  eligible INTEGER DEFAULT 0, selected INTEGER DEFAULT 0, notes TEXT);
CREATE TABLE IF NOT EXISTS video_scores(
  id INTEGER PRIMARY KEY AUTOINCREMENT, video_id INTEGER NOT NULL, scan_id INTEGER NOT NULL,
  score REAL, components_json TEXT, explanation TEXT, outcome TEXT, reason TEXT, created_at REAL,
  UNIQUE(video_id, scan_id));
CREATE TABLE IF NOT EXISTS downloads(
  id INTEGER PRIMARY KEY AUTOINCREMENT, video_id INTEGER NOT NULL UNIQUE, path TEXT, status TEXT,
  error TEXT, attempts INTEGER DEFAULT 0, updated_at REAL);
CREATE TABLE IF NOT EXISTS processed_videos(
  id INTEGER PRIMARY KEY AUTOINCREMENT, video_id INTEGER NOT NULL, preset TEXT, path TEXT,
  status TEXT, error TEXT, updated_at REAL, UNIQUE(video_id, preset));
CREATE TABLE IF NOT EXISTS upload_queue(
  id INTEGER PRIMARY KEY AUTOINCREMENT, video_id INTEGER NOT NULL UNIQUE, title TEXT, description TEXT,
  hashtags TEXT, visibility TEXT DEFAULT 'private', schedule_at TEXT, approval TEXT DEFAULT 'PENDING',
  status TEXT DEFAULT 'QUEUED', updated_at REAL);
CREATE TABLE IF NOT EXISTS upload_history(
  id INTEGER PRIMARY KEY AUTOINCREMENT, video_id INTEGER NOT NULL, youtube_video_id TEXT, youtube_url TEXT,
  status TEXT, error TEXT, uploaded_at REAL);
CREATE TABLE IF NOT EXISTS content_permissions(
  id INTEGER PRIMARY KEY AUTOINCREMENT, platform TEXT, creator_key TEXT, status TEXT, note TEXT,
  updated_at REAL, UNIQUE(platform, creator_key));
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS scan_errors(
  id INTEGER PRIMARY KEY AUTOINCREMENT, scan_id INTEGER, ts REAL, module TEXT, operation TEXT,
  video_id TEXT, source TEXT, error TEXT, retry_count INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS state_log(
  id INTEGER PRIMARY KEY AUTOINCREMENT, video_id INTEGER NOT NULL, from_state TEXT, to_state TEXT,
  ts REAL, note TEXT);
"""


class DB:
    def __init__(self, path=DB_PATH):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=DELETE")  # single file: easy to commit to git
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    @contextmanager
    def tx(self):
        try:
            yield self.conn
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def close(self):
        self.conn.close()

    # ---- settings / quota
    def get_setting(self, key, default=None):
        r = self.conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return r["value"] if r else default

    def set_setting(self, key, value):
        with self.tx() as c:
            c.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                      (key, str(value)))

    # ---- scans & errors
    def start_scan(self, scan_date) -> int:
        with self.tx() as c:
            cur = c.execute("INSERT INTO daily_scans(scan_date,started_at,status) VALUES(?,?,?)",
                            (scan_date, time.time(), "RUNNING"))
            return cur.lastrowid

    def finish_scan(self, scan_id, status, discovered, rejected, duplicates, eligible, selected, notes=""):
        with self.tx() as c:
            c.execute("""UPDATE daily_scans SET finished_at=?,status=?,discovered=?,rejected=?,duplicates=?,
                         eligible=?,selected=?,notes=? WHERE id=?""",
                      (time.time(), status, discovered, rejected, duplicates, eligible, selected, notes, scan_id))

    def log_error(self, scan_id, module, operation, error, video_id="", source="", retry_count=0):
        with self.tx() as c:
            c.execute("""INSERT INTO scan_errors(scan_id,ts,module,operation,video_id,source,error,retry_count)
                         VALUES(?,?,?,?,?,?,?,?)""",
                      (scan_id, time.time(), module, operation, video_id, source, str(error)[:1000], retry_count))

    # ---- videos
    def get_video(self, platform, source_id):
        return self.conn.execute("SELECT * FROM discovered_videos WHERE platform=? AND source_id=?",
                                 (platform, source_id)).fetchone()

    def upsert_candidate(self, c) -> int:
        """Insert or refresh. Returns row id. Sets c.previously_seen."""
        now = time.time()
        row = self.get_video(c.platform, c.source_id)
        with self.tx() as conn:
            if row:
                c.previously_seen = True
                conn.execute("""UPDATE discovered_videos SET last_seen=?, times_seen=times_seen+1,
                    views=COALESCE(?,views), likes=COALESCE(?,likes), comments=COALESCE(?,comments),
                    duration=COALESCE(?,duration), published_ts=COALESCE(?,published_ts),
                    thumbnail=CASE WHEN ?!='' THEN ? ELSE thumbnail END, title=?, creator_name=?
                    WHERE id=?""",
                             (now, c.views, c.likes, c.comments, c.duration, c.published_ts,
                              c.thumbnail, c.thumbnail, c.title, c.creator, row["id"]))
                return row["id"]
            cur = conn.execute("""INSERT INTO discovered_videos(platform,source_id,url,title,kind,creator_id,
                creator_name,published_ts,duration,views,likes,comments,thumbnail,description,keyword,
                content_type,relevance,is_short,is_official,downloadable,license,rights_status,first_seen,last_seen)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                               (c.platform, c.source_id, c.url, c.title, c.kind, c.creator_id, c.creator,
                                c.published_ts, c.duration, c.views, c.likes, c.comments, c.thumbnail,
                                c.description[:2000], c.keyword, c.content_type, c.relevance,
                                None if c.is_short is None else int(c.is_short), int(c.is_official),
                                None if c.downloadable is None else int(c.downloadable), c.license,
                                c.rights, now, now))
            return cur.lastrowid

    def previous_selection(self, video_id):
        r = self.conn.execute("SELECT selected_date FROM discovered_videos WHERE id=?", (video_id,)).fetchone()
        return r["selected_date"] if r else None

    def set_state(self, video_id, new_state, note="", selected_date=None):
        r = self.conn.execute("SELECT status FROM discovered_videos WHERE id=?", (video_id,)).fetchone()
        old = r["status"] if r else None
        with self.tx() as c:
            if selected_date:
                c.execute("UPDATE discovered_videos SET status=?, selected_date=?, rights_status=rights_status WHERE id=?",
                          (new_state, selected_date, video_id))
            else:
                c.execute("UPDATE discovered_videos SET status=? WHERE id=?", (new_state, video_id))
            if old != new_state:
                c.execute("INSERT INTO state_log(video_id,from_state,to_state,ts,note) VALUES(?,?,?,?,?)",
                          (video_id, old, new_state, time.time(), note[:300]))

    def update_classification(self, video_id, c):
        with self.tx() as conn:
            conn.execute("""UPDATE discovered_videos SET content_type=?, relevance=?, rights_status=?,
                            is_short=?, downloadable=? WHERE id=?""",
                         (c.content_type, c.relevance, c.rights,
                          None if c.is_short is None else int(c.is_short),
                          None if c.downloadable is None else int(c.downloadable), video_id))

    def save_score(self, video_id, scan_id, c):
        with self.tx() as conn:
            conn.execute("""INSERT INTO video_scores(video_id,scan_id,score,components_json,explanation,outcome,reason,created_at)
                VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(video_id,scan_id) DO UPDATE SET score=excluded.score,
                components_json=excluded.components_json, explanation=excluded.explanation,
                outcome=excluded.outcome, reason=excluded.reason""",
                         (video_id, scan_id, c.score, json.dumps(c.components), c.explanation,
                          c.status, c.reason, time.time()))

    # ---- creators
    def upsert_creator(self, platform, channel_id, name, followers):
        if not channel_id:
            return
        with self.tx() as c:
            c.execute("""INSERT INTO creators(platform,channel_id,name,follower_count,last_seen) VALUES(?,?,?,?,?)
                ON CONFLICT(platform,channel_id) DO UPDATE SET name=excluded.name,
                follower_count=COALESCE(excluded.follower_count, follower_count), last_seen=excluded.last_seen""",
                      (platform, channel_id, name, followers, time.time()))

    def creator_followers(self, platform, channel_id):
        r = self.conn.execute("SELECT follower_count FROM creators WHERE platform=? AND channel_id=?",
                              (platform, channel_id)).fetchone()
        return r["follower_count"] if r else None

    def creator_view_history(self, platform, creator_id, exclude_source_id):
        rows = self.conn.execute("""SELECT views FROM discovered_videos WHERE platform=? AND creator_id=?
                                    AND source_id!=? AND views IS NOT NULL""",
                                 (platform, creator_id, exclude_source_id)).fetchall()
        return [r["views"] for r in rows]

    def sync_permissions(self, entries):
        with self.tx() as c:
            for e in entries:
                c.execute("""INSERT INTO content_permissions(platform,creator_key,status,note,updated_at) VALUES(?,?,?,?,?)
                    ON CONFLICT(platform,creator_key) DO UPDATE SET status=excluded.status,note=excluded.note,
                    updated_at=excluded.updated_at""",
                          (e.get("platform", "youtube"), e["name"].lower(), e["status"], e.get("note", ""), time.time()))

    def permission_for(self, platform, creator_name):
        r = self.conn.execute("SELECT status FROM content_permissions WHERE platform=? AND creator_key=?",
                              (platform, (creator_name or "").lower())).fetchone()
        return r["status"] if r else None
