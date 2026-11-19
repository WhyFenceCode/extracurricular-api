"""Health Sciences Society (Bachelor of Health Sciences) ratified clubs.

The Squarespace page repeats one pattern per club, as consecutive text blocks:
description, then the club name, then a "Contact Us ... Instagram: @handle" block.
"""

from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup

from ..http import PoliteClient
from ..text import clean_text

SOURCE_ID = "queens-hss"
SOURCE_NAME = "Queen's Health Sciences Society (HSS)"
URL = "https://www.queenshss.ca/hss-ratified-clubs"
# "@handle", but not the "@domain" of an email address (preceded by a word character).
_HANDLE = re.compile(r"(?<![\w.])@([A-Za-z0-9._]{2,30})")


def fetch(client: PoliteClient) -> dict[str, Any]:
    return {"html": client.get(URL).text, "via": "live", "origin_url": URL}


def parse(raw: dict[str, Any]) -> list[dict[str, Any]]:
    soup = BeautifulSoup(raw["html"], "html.parser")
    main = soup.find("main") or soup
    texts = [clean_text(b.get_text(" ")) for b in main.select(".sqs-block")]
    texts = [t for t in texts if t and t != "HSS Ratified Clubs"]
    out = []
    for i, t in enumerate(texts):
        if not t.lower().startswith("contact us") or i < 2:
            continue
        name, desc = texts[i - 1], texts[i - 2]
        if desc.lower().startswith("contact us") or len(name) > 120:
            continue  # pattern broken; skip rather than mislabel
        m = _HANDLE.search(t)
        out.append({
            "key": name,
            "name": name,
            "description": desc,
            "listing_url": URL,
            "website": None,
            "instagram": f"https://www.instagram.com/{m.group(1).rstrip('.')}/" if m else None,
            "categories": [],
            "updated_at": None,
            "kind": "hss-club",
        })
    # The page has copy-paste errors (one club shows another's Instagram). A handle that
    # appears on more than one club can't be attributed, so drop it from all of them.
    seen: dict[str, int] = {}
    for r in out:
        if r["instagram"]:
            seen[r["instagram"]] = seen.get(r["instagram"], 0) + 1
    for r in out:
        if r["instagram"] and seen[r["instagram"]] > 1:
            r["instagram"] = None
    return out
