import html
import re

TAG_RE = re.compile(r"<[^>]+>")
SPACES_RE = re.compile(r"[ \t\u00a0]+")
NEWLINES_RE = re.compile(r"\n{3,}")
ANTISPAM_RE = re.compile(r"please mention the word.*", re.IGNORECASE | re.DOTALL)
MOJIBAKE_MARKERS = ("\u00e2\u0080", "\u00c3", "\u00c2")

MAX_DESCRIPTION_CHARS = 20_000


def fix_mojibake(text: str) -> str:
    """Repair double-encoded UTF-8 (latin-1 roundtrip). Applied only when markers present."""
    if not any(m in text for m in MOJIBAKE_MARKERS):
        return text
    try:
        repaired = text.encode("latin-1", "ignore").decode("utf-8", "ignore")
        # Sanity: repair must not destroy most of the text
        if len(repaired) >= len(text) * 0.5:
            return repaired
    except (UnicodeError, ValueError):
        pass
    return text


def strip_html(text: str) -> str:
    text = re.sub(r"<(br|/p|/div|/li|/h\d)[^>]*>", "\n", text, flags=re.IGNORECASE)
    text = TAG_RE.sub(" ", text)
    text = html.unescape(text)
    return text


def clean_description(raw_html: str) -> str:
    if not raw_html:
        return ""
    text = strip_html(raw_html)
    text = fix_mojibake(text)
    text = ANTISPAM_RE.sub("", text)
    text = SPACES_RE.sub(" ", text)
    text = NEWLINES_RE.sub("\n\n", text)
    return text.strip()[:MAX_DESCRIPTION_CHARS]


def normalize_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()
