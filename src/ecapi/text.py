from __future__ import annotations

import html
import re
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from bs4 import BeautifulSoup

_TRACKING = re.compile(r"^(utm_.*|fbclid|gclid|igshid|mc_[a-z]+|si)$", re.I)


def slugify(s: str) -> str:
    s = unicodedata.normalize("NFKD", html.unescape(s)).encode("ascii", "ignore").decode()
    s = s.lower().replace("&", " ").replace("'", "")
    s = re.sub(r"\band\b", " ", s)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s


def clean_text(s: str) -> str:
    s = html.unescape(s).replace(" ", " ")
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    s = s.replace("�", "'")  # mis-encoded apostrophes on some source pages
    return re.sub(r"\s+", " ", s).strip()


def html_to_text(fragment: str) -> str:
    soup = BeautifulSoup(fragment, "html.parser")
    for tag in soup(["img", "script", "style"]):
        tag.decompose()
    return clean_text(soup.get_text(" "))


def strip_tracking(url: str) -> str:
    parts = urlsplit(url.strip())
    q = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if not _TRACKING.match(k)]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(q), ""))


def is_instagram(url: str) -> bool:
    return "instagram.com" in urlsplit(url).netloc


def normalize_instagram(url: str) -> str:
    p = urlsplit(url)
    return urlunsplit(("https", "www.instagram.com", p.path.rstrip("/") + "/", "", ""))
