"""Entry point.  python run.py scan   |   python run.py demo   |   python run.py check"""
import argparse, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app.core.logging_config import setup_logging


def main():
    p = argparse.ArgumentParser(description="GTA 6 Shorts discovery pipeline")
    p.add_argument("command", choices=["scan", "demo", "check"], help="scan = real daily scan; demo = offline sample data; check = verify setup")
    p.add_argument("--window-hours", type=int, help="override time window (24, 72, 168 or custom)")
    a = p.parse_args()
    setup_logging()
    from app.core import config
    if a.command == "check":
        import shutil
        print("python:", sys.version.split()[0])
        for mod in ("yt_dlp", "feedparser", "requests"):
            try:
                __import__(mod); print(f"{mod}: OK")
            except ImportError:
                print(f"{mod}: MISSING (pip install -r requirements.txt)")
        print("YOUTUBE_API_KEY set:", bool(config.youtube_api_key()), "(optional)")
        print("ffmpeg on PATH:", bool(shutil.which("ffmpeg")), "(needed from Phase 3/4)")
        return 0
    settings = config.load_settings()
    if a.window_hours:
        settings["window_hours"] = a.window_hours
    if a.command == "demo":
        from tests.demo_data import demo_collectors
        from app.core.database import DB
        from app.core import pipeline
        demo_db = config.DATA_DIR / "demo.db"
        if demo_db.exists():
            demo_db.unlink()
        s, _ = pipeline.run_scan(collectors=demo_collectors(), settings=settings, db=DB(demo_db))
    else:
        from app.core import pipeline
        s, _ = pipeline.run_scan(settings=settings)
    print("\nSUMMARY:", s)
    print("Open:", config.REPORT_DIR / "latest.html")
    return 0


if __name__ == "__main__":
    sys.exit(main())
