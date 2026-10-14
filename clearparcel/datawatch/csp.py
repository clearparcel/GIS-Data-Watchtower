"""Content-Security-Policy that allows only scripts Watchtower's own code wrote.

Every inline script the templates emit opens with ``SCRIPT_TAG``, which carries
an attribute whose name is random per process. Before a response is sent,
``secure_html`` hashes exactly those scripts (SHA-256), removes the marker,
and returns a policy listing the hashes. A ``<script>`` that reached the page
through data, for example an escaping failure, has no marker, so it is not
hashed and the browser refuses to run it. Event-handler attributes are not
used, so they are blocked too (no ``'unsafe-inline'``/``'unsafe-hashes'``).

Hashes are computed on the response body, so cached pages and 304
revalidation keep working. Inline styles keep ``'unsafe-inline'``.
"""
from __future__ import annotations

import base64
import hashlib
import re
import secrets

_MARK = "data-wt-" + secrets.token_hex(12)
SCRIPT_TAG = f"<script {_MARK}>"

_CLOSE = re.compile(r"</script", re.IGNORECASE)


def _hash(body: str) -> str:
    # Browsers hash the script text after input-stream newline normalization.
    normalized = body.replace("\r\n", "\n").replace("\r", "\n")
    return "'sha256-" + base64.b64encode(hashlib.sha256(normalized.encode("utf-8")).digest()).decode("ascii") + "'"


def trusted_script_hashes(html: str) -> list[str]:
    """Hashes of the inline scripts that carry this process's marker, in page order."""
    hashes, cursor = [], 0
    while True:
        start = html.find(SCRIPT_TAG, cursor)
        if start == -1:
            return hashes
        body_start = start + len(SCRIPT_TAG)
        close = _CLOSE.search(html, body_start)
        if close is None:
            return hashes
        source = _hash(html[body_start:close.start()])
        if source not in hashes:
            hashes.append(source)
        cursor = close.end()


def policy(script_hashes: list[str], *, script_origins: tuple[str, ...] = (),
           connect_origins: tuple[str, ...] = ()) -> str:
    script_src = " ".join(("'self'", *script_hashes, *script_origins))
    connect_src = " ".join(("'self'", *connect_origins))
    return ("default-src 'self'; style-src 'self' 'unsafe-inline'; "
            f"script-src {script_src}; connect-src {connect_src}; "
            "img-src 'self' data:; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")


def strip_markers(html: str) -> str:
    """Remove the per-process marker (used for output that is not served with a policy)."""
    return html.replace(" " + _MARK, "")


def secure_html(html: str, *, script_origins: tuple[str, ...] = (),
                connect_origins: tuple[str, ...] = ()) -> tuple[str, str]:
    """Return the HTML to send (markers removed) and its Content-Security-Policy."""
    return strip_markers(html), policy(trusted_script_hashes(html), script_origins=script_origins,
                                       connect_origins=connect_origins)
