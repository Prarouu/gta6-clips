import logging, sys
from logging.handlers import RotatingFileHandler
from app.core.config import LOG_DIR


def setup_logging(level=logging.INFO):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s | %(name)s | %(levelname)s | %(message)s")
    root = logging.getLogger()
    root.setLevel(level)
    for h in list(root.handlers):
        root.removeHandler(h)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    fh = RotatingFileHandler(LOG_DIR / "run.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(sh)
    root.addHandler(fh)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def kv(**fields) -> str:
    """Structured log suffix: op=search video_id=abc source=youtube retry=1"""
    return " ".join(f"{k}={v}" for k, v in fields.items() if v not in (None, ""))
