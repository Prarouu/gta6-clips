import logging
from dataclasses import dataclass, field
from app.core.logging_config import kv


@dataclass
class Ctx:
    db: object
    settings: dict
    keywords: dict
    scan_id: int
    now_ts: float
    api_key: str = ""
    day_index: int = 0     # used to rotate keywords so every keyword is covered over several days
    log: logging.Logger = field(default_factory=lambda: logging.getLogger("pipeline"))

    def err(self, module, operation, error, video_id="", source="", retry=0):
        self.log.error(kv(module=module, op=operation, video_id=video_id, source=source, retry=retry, error=str(error)[:300]))
        try:
            self.db.log_error(self.scan_id, module, operation, error, video_id, source, retry)
        except Exception as e:  # never let error logging break the scan
            self.log.error("could not write scan_error: %s", e)

    def rotate(self, items, n):
        """Pick n items starting at a daily-rotating offset."""
        if not items or n >= len(items):
            return list(items)
        start = (self.day_index * n) % len(items)
        return [items[(start + i) % len(items)] for i in range(n)]
