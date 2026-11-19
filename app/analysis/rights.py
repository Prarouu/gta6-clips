from app.core.models import RIGHTS


def determine_rights(c, db):
    """Never assumes permission. CC license detected from metadata still needs manual verification."""
    override = db.permission_for(c.platform, c.creator)
    if override in RIGHTS:
        c.rights = override
    elif "creative" in (c.license or "").lower():
        c.rights = "CREATIVE_COMMONS"
        c.warnings.append("Marked Creative Commons by the platform - open the video page and confirm the exact licence and attribution rules before reuse.")
    elif c.is_official:
        c.rights = "PERMISSION_REQUIRED"
    else:
        c.rights = "UNKNOWN"
    if c.kind != "video":
        c.downloadable = False
    return c.rights


def apply_warnings(c, settings):
    if c.rights not in settings["auto_publish_rights"]:
        c.warnings.append(f"RIGHTS: {c.rights} - not eligible for automatic upload. Discovery/ranking only. "
                          "Cropping, subtitles or zooming does not make someone else's clip safe to repost; "
                          "consider original commentary or ask the creator for permission.")
    if c.content_type == "leak_rumor":
        c.warnings.append("UNVERIFIED: leak/rumour content. Label it clearly as unconfirmed; never present it as fact.")
