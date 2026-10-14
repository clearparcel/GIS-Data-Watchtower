"""Markup-text helpers so UI tests survive markup and line-wrapping changes.

These read the text in the HTML, not what a browser finally shows: content in
`hidden` elements or hidden by CSS still counts. Visibility itself is checked
in the browser (axe/Playwright) during UI work, not by these unit tests.
"""
import html
import re

_HIDDEN = re.compile(r"<(script|style|template)\b[^>]*>.*?</\1\s*>", re.S | re.I)
_TAG = re.compile(r"<[^>]*>")


def page_text(markup: str) -> str:
    """Return the page's text (scripts, styles and templates removed), whitespace collapsed."""
    text = _TAG.sub(" ", _HIDDEN.sub(" ", markup))
    return " ".join(html.unescape(text).split())


def metric(markup: str, label: str) -> str | None:
    """Return the first visible token after a metric label.

    The label must appear exactly once (as a whole phrase) so a nav item or
    sentence elsewhere cannot silently become the match.
    """
    text = page_text(markup)
    matches = list(re.finditer(r"(?<!\w)" + re.escape(label) + r"(?!\w)", text))
    if len(matches) != 1:
        raise AssertionError(f"metric label {label!r} appears {len(matches)} times in the page text")
    rest = text[matches[0].end():].split()
    return rest[0] if rest else None
