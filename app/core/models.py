from dataclasses import dataclass, field
from typing import Optional

RIGHTS = ["ORIGINAL", "LICENSED", "CREATOR_PERMISSION", "PUBLIC_DOMAIN", "CREATIVE_COMMONS",
          "PERMISSION_REQUIRED", "UNKNOWN", "RESTRICTED"]


@dataclass
class Candidate:
    platform: str                  # youtube | reddit | news
    source_id: str
    url: str
    title: str
    kind: str = "video"            # video | post | article
    creator: str = ""
    creator_id: str = ""
    published_ts: Optional[float] = None
    duration: Optional[float] = None
    views: Optional[int] = None
    likes: Optional[int] = None
    comments: Optional[int] = None
    thumbnail: str = ""
    description: str = ""
    keyword: str = ""
    connector: str = ""
    is_short: Optional[bool] = None
    is_official: bool = False
    downloadable: Optional[bool] = None
    license: str = ""
    height: Optional[int] = None
    follower_count: Optional[int] = None
    # computed by the pipeline
    content_type: str = "other"
    relevance: float = 0.0
    rights: str = "UNKNOWN"
    previously_seen: bool = False
    score: float = 0.0
    components: dict = field(default_factory=dict)
    explanation: str = ""
    status: str = "DISCOVERED"     # DISCOVERED | SELECTED | LEAD | REJECTED | DUPLICATE
    reason: str = ""
    warnings: list = field(default_factory=list)
    dup_of: str = ""

    @property
    def key(self):
        return f"{self.platform}:{self.source_id}"
