"""Rich-text sanitising — the only place untrusted HTML becomes renderable.

plan.md §9.3 rule 3 ("``rich_text`` bodies pass through ``bleach`` with a strict
allowlist on save AND on render") and §12.2.

═══════════════════════════════════════════════════════════════════════════════
THE BLEACH GOTCHA — VERIFIED IN PHASE 1, NOT ASSUMED
    ``bleach.clean(..., strip=True)`` removes disallowed TAGS but KEEPS their text
    content:

        <p>ok</p><script>alert(1)</script>   ->   <p>ok</p>alert(1)

    The leftover text is inert once Jinja escapes it, so this is not an XSS hole —
    but it renders as the literal words "alert(1)" in the middle of a government
    page, and a writer who pasted from a Word document will have no idea where it
    came from. So script and style BLOCKS are removed before bleach ever sees the
    string.
═══════════════════════════════════════════════════════════════════════════════

APPLIED ON SAVE **AND** ON RENDER. Sanitising only on write means every row that
predates a tightened allowlist stays dangerous forever; sanitising only on read
means the database is a store of hostile strings that a future feature might
export. Both are cheap. Do both.
"""

from __future__ import annotations

import re

import bleach

#: The allowlist. Deliberately short: these are the tags the section templates can
#: style. Anything else is not "unsupported", it is refused.
ALLOWED_TAGS: tuple[str, ...] = (
    "p", "br", "strong", "b", "em", "i", "u",
    "ul", "ol", "li",
    "h3", "h4",
    "a", "blockquote",
)

ALLOWED_ATTRIBUTES: dict[str, list[str]] = {
    "a": ["href", "title", "rel", "target"],
}

#: No mailto by default would break the contact page; no `data:` — a data URL in an
#: href is a redirect primitive, and there is no legitimate use for one here.
ALLOWED_PROTOCOLS: tuple[str, ...] = ("http", "https", "mailto")

#: `script`/`style` blocks AND their contents. The `.*?` is non-greedy so two
#: script blocks on one line are both removed, and DOTALL lets a block span lines.
#: An unterminated `<script>` with no closing tag is caught by the second pattern.
_SCRIPT_STYLE_BLOCK = re.compile(r"<(script|style)\b[^>]*>.*?</\1\s*>", re.S | re.I)
_UNTERMINATED_BLOCK = re.compile(r"<(script|style)\b[^>]*>.*$", re.S | re.I)
#: HTML comments are removed too: a comment can carry a conditional comment or a
#: server-side include directive in a template that is later rendered differently.
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)
#: Control characters except tab, newline and carriage return.
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def sanitize_html(raw: str | None) -> str:
    """Return HTML that is safe to render on a government page.

    Applied on save and again on render. Idempotent, so applying it twice is not a
    mistake — which matters, because the two call sites cannot see each other.
    """
    if not raw:
        return ""

    text = str(raw)
    text = _HTML_COMMENT.sub("", text)
    text = _SCRIPT_STYLE_BLOCK.sub("", text)
    text = _UNTERMINATED_BLOCK.sub("", text)
    text = _CONTROL_CHARS.sub("", text)

    cleaned = bleach.clean(
        text,
        tags=list(ALLOWED_TAGS),
        attributes=ALLOWED_ATTRIBUTES,
        protocols=list(ALLOWED_PROTOCOLS),
        strip=True,
        strip_comments=True,
    )

    # Belt: a `javascript:` that survived in an odd form (mixed case, embedded
    # entities) would be stripped by bleach's protocol check, but a link whose href
    # then vanished should not render as a clickable `<a>` with no destination.
    cleaned = re.sub(r"<a\b[^>]*>\s*</a>", "", cleaned, flags=re.I)

    return cleaned.strip()


def looks_like_html(value: str | None) -> bool:
    """True when a value contains tags. Used to decide whether to warn on save."""
    if not value:
        return False
    return bool(re.search(r"<[a-zA-Z/][^>]*>", value))


def plain_text(raw: str | None, *, limit: int | None = None) -> str:
    """Tags removed entirely, whitespace collapsed — for meta descriptions."""
    if not raw:
        return ""
    text = _HTML_COMMENT.sub(" ", str(raw))
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if limit and len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text


__all__ = ["ALLOWED_ATTRIBUTES", "ALLOWED_PROTOCOLS", "ALLOWED_TAGS",
           "looks_like_html", "plain_text", "sanitize_html"]
