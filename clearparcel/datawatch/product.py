"""Official product name.

User-facing titles, headers, alerts, exports, and request identity use
``PRODUCT_NAME``. Do not copy the name into another constant.
"""

PRODUCT_NAME = "ClearParcel GIS Data Watchtower"


def page_title(specific: str | None = None) -> str:
    """Document title. The overview is the official name alone."""
    label = "" if specific is None else str(specific).strip()
    if not label or label == PRODUCT_NAME:
        return PRODUCT_NAME
    return f"{label} — {PRODUCT_NAME}"


def page_label(title: str) -> str:
    """Visible page name with the official product name removed."""
    suffix = f" — {PRODUCT_NAME}"
    prefix = f"{PRODUCT_NAME} — "
    if title == PRODUCT_NAME:
        return "Overview"
    if title.endswith(suffix):
        return title[: -len(suffix)]
    if title.startswith(prefix):
        return title[len(prefix):]
    return title
