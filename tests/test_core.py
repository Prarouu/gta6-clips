import tempfile, unittest, time
from pathlib import Path
from app.core.database import DB
from app.core.models import Candidate
from app.core import config, pipeline
from app.analysis import scoring
from app.analysis.duplicate_detection import similar
from tests.demo_data import demo_collectors


class T(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = DB(Path(self.tmp.name) / "t.db")
        self.s = config.load_settings()

    def tearDown(self):
        self.db.close(); self.tmp.cleanup()

    def test_relevance(self):
        kw = config.load_keywords()
        self.assertEqual(scoring.relevance_score("GTA 6 map", "", kw), 100)
        self.assertEqual(scoring.relevance_score("Minecraft", "", kw), 0)

    def test_duplicate_similarity(self):
        self.assertTrue(similar("GTA 6 leaked map comparison vs GTA 5", "GTA 6 leaked map comparison versus GTA V"))
        self.assertFalse(similar("GTA 6 trailer breakdown", "GTA 6 funny moments"))

    def test_small_creator_outranks_big_creator_same_views(self):
        now = time.time(); kw = config.load_keywords()
        def mk(subs):
            c = Candidate(platform="youtube", source_id=str(subs), url=str(subs), title="GTA 6 clip", views=100000,
                          likes=5000, comments=400, duration=40, published_ts=now - 5 * 3600, follower_count=subs)
            c.relevance = 100
            return scoring.score_candidate(c, self.s, now, {"gta": 1})
        self.assertGreater(mk(1000).score, mk(5_000_000).score)

    def test_missing_metrics_not_invented(self):
        now = time.time()
        c = Candidate(platform="reddit", source_id="x", url="x", title="GTA 6 news", kind="post", published_ts=now - 3600)
        c.relevance = 100
        scoring.score_candidate(c, self.s, now, {})
        self.assertIsNone(c.components["engagement"]["score"])
        self.assertIn("ESTIMATE", c.explanation)

    def test_full_pipeline_isolated_failure_and_dedupe(self):
        self.s["daily_target_max"] = 15
        summary, ranked = pipeline.run_scan(collectors=demo_collectors(), settings=self.s, db=self.db, write=False)
        by = {c.source_id: c for c in ranked}
        self.assertEqual(by["demo010"].status, "REJECTED")            # irrelevant
        self.assertEqual(by["demo011"].status, "REJECTED")            # too old
        self.assertEqual(by["demo009"].status, "DUPLICATE")           # near-dup of demo002
        self.assertEqual(by["demo002"].status, "SELECTED")
        self.assertGreaterEqual(summary["errors"], 1)                 # broken source logged, scan continued
        self.assertGreater(summary["selected"], 0)
        self.assertTrue(all(c.rights != "ORIGINAL" for c in ranked))  # never assumes permission
        self.assertEqual(by["demo008"].rights, "CREATIVE_COMMONS")
        self.assertTrue(any("RIGHTS" in w for w in by["demo001"].warnings))
        self.assertEqual(by["r1"].status, "LEAD")
        self.assertTrue(any("UNVERIFIED" in w for w in by["r1"].warnings))

    def test_second_run_does_not_reselect_same_day_items_twice_in_db(self):
        pipeline.run_scan(collectors=demo_collectors(), settings=self.s, db=self.db, write=False)
        n1 = self.db.conn.execute("SELECT COUNT(*) n FROM discovered_videos").fetchone()["n"]
        pipeline.run_scan(collectors=demo_collectors(), settings=self.s, db=self.db, write=False)
        n2 = self.db.conn.execute("SELECT COUNT(*) n FROM discovered_videos").fetchone()["n"]
        self.assertEqual(n1, n2)                                     # unique constraints hold


if __name__ == "__main__":
    unittest.main()
