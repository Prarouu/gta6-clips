"""Synthetic candidates so the pipeline can be tested with no internet. NOT real videos."""
import time
from app.core.models import Candidate

H = 3600


def _v(i, title, hours, views, likes, comments, dur, creator, subs, **kw):
    now = time.time()
    return Candidate(platform="youtube", source_id=f"demo{i:03d}", url=f"https://www.youtube.com/watch?v=demo{i:03d}",
                     title=title, creator=creator, creator_id=f"UC{creator}", published_ts=now - hours * H, duration=dur,
                     views=views, likes=likes, comments=comments, follower_count=subs, keyword="demo",
                     connector="youtube_search", downloadable=True, thumbnail="", **kw)


def demo_collectors():
    def yt(ctx):
        out = [
            _v(1, "GTA 6 Lucia gameplay hidden detail you missed", 5, 450000, 31000, 2100, 42, "TinyGamer", 8000),
            _v(2, "GTA 6 leaked map comparison vs GTA 5", 20, 120000, 6000, 900, 55, "MapNerd", 150000, height=1080),
            _v(3, "GTA 6 streamer reaction to the trailer", 30, 800000, 40000, 5000, 58, "BigStreamer", 4000000),
            _v(4, "GTA VI Vice City funny moments", 12, 30000, 2500, 300, 35, "FunnyGuy", 20000),
            _v(5, "GTA 6 release date news confirmed?", 8, 220000, 9000, 1500, 640, "NewsDaily", 900000),
            _v(6, "Grand Theft Auto VI new vehicles revealed", 40, 90000, 4000, 400, 75, "CarFan", 50000),
            _v(7, "GTA 6 Jason and Lucia theory explained", 60, 70000, 3500, 700, 170, "TheoryHub", 300000),
            _v(8, "GTA 6 insane physics first look", 3, 15000, 1200, 150, 30, "NewKid", 500, license="Creative Commons Attribution license (reuse allowed)"),
            _v(9, "GTA 6 leaked map comparison versus GTA V", 22, 60000, 2000, 300, 50, "CopyCat", 10000),   # near-duplicate of #2
            _v(10, "Minecraft speedrun world record", 4, 900000, 50000, 3000, 50, "Speedy", 100000),        # irrelevant
            _v(11, "GTA 6 trailer 3 breakdown", 400, 5000000, 200000, 20000, 600, "OldNews", 2000000),     # too old
            _v(12, "Rockstar Games new job posting", 10, 12000, 800, 90, 45, "Insider", 30000),
        ]
        out[1].connector = "youtube_search"
        return out

    def reddit(ctx):
        now = time.time()
        return [Candidate(platform="reddit", source_id="r1", url="https://reddit.com/r/GTA6/comments/r1/x/",
                          title="GTA 6 leak: new insider claims about online mode", kind="post", creator="user1",
                          published_ts=now - 6 * H, keyword="r/GTA6", connector="reddit", downloadable=False)]

    def news(ctx):
        now = time.time()
        return [Candidate(platform="news", source_id="n1", url="https://example.com/n1", kind="article",
                          title="Rockstar confirms GTA 6 release update", creator="IGN", published_ts=now - 9 * H,
                          keyword="news feed", connector="news_rss", downloadable=False),
                Candidate(platform="news", source_id="n2", url="https://example.com/n2", kind="article",
                          title="GTA VI release date news: what Rockstar said", creator="GameSpot",
                          published_ts=now - 10 * H, keyword="news feed", connector="news_rss", downloadable=False)]

    def broken(ctx):
        raise RuntimeError("simulated source outage")

    return {"youtube_search": yt, "reddit": reddit, "news_rss": news, "youtube_channels": broken, "youtube_api": lambda c: []}
