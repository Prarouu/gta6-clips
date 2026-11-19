import difflib, re
from app.analysis.scoring import tokens


def _norm(title):
    return " ".join(tokens(title))


def similar(a, b, jaccard=0.6, ratio=0.85) -> bool:
    ta, tb = set(tokens(a)), set(tokens(b))
    if not ta or not tb:
        return False
    j = len(ta & tb) / len(ta | tb)
    return j >= jaccard or difflib.SequenceMatcher(None, _norm(a), _norm(b)).ratio() >= ratio


def mark_duplicates(ranked):
    """ranked: candidates sorted best-first. Later near-duplicates are marked DUPLICATE (best one is kept)."""
    keepers = []
    n = 0
    for c in ranked:
        if c.status in ("REJECTED",):
            continue
        hit = next((k for k in keepers if k.kind == c.kind and similar(k.title, c.title)), None)
        if hit:
            c.status, c.reason, c.dup_of = "DUPLICATE", f"similar to higher-ranked item: {hit.title[:70]}", hit.key
            n += 1
        else:
            keepers.append(c)
    return n
