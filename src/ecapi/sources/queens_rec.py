"""Queen's Athletics & Recreation: sanctioned recreational clubs.

One page and one paragraph per club, separated by <hr>: a bold club name, a
description, then contact lines. Executives' names are on the page too, but we
deliberately don't collect them (no personal data).
"""

from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup, NavigableString, Tag

from ..http import PoliteClient
from ..text import clean_text, is_instagram, normalize_instagram, strip_tracking

SOURCE_ID = "queens-rec"
SOURCE_NAME = "Queen's Athletics & Recreation: Recreational Clubs"
URL = "https://rec.gogaelsgo.com/sports/2013/7/31/Clubs_0731135902.aspx"
_STOP = re.compile(r"^(co-?presidents?|presidents?|club email|email|contact)\b", re.I)


def fetch(client: PoliteClient) -> dict[str, Any]:
    return {"html": client.get(URL).text, "via": "live", "origin_url": URL}


def _norm(name: str) -> str:
    n = re.sub(r"\([^)]*\)", "", name.lower())
    n = re.sub(r"\b(queen'?s|club|recreational|team)\b", " ", n)
    return re.sub(r"[^a-z]+", "", n)


def _categories(article: Tag) -> dict[str, str]:
    """The tab table at the top: one column per category, club names underneath."""
    table = article.find("table")
    if not table:
        return {}
    rows = table.find_all("tr")
    if not rows:
        return {}
    heads = [clean_text(c.get_text(" ")) for c in rows[0].find_all(["td", "th"])]
    cats: dict[str, str] = {}
    for r in rows[1:]:
        for i, cell in enumerate(r.find_all(["td", "th"])):
            name = clean_text(cell.get_text(" "))
            if name and i < len(heads):
                cats[_norm(name)] = heads[i]
    return cats


def parse(raw: dict[str, Any]) -> list[dict[str, Any]]:
    soup = BeautifulSoup(raw["html"], "html.parser")
    article = soup.select_one("article") or soup
    cats = _categories(article)
    out, seen = [], set()
    for p in article.find_all("p"):
        bold = p.find(lambda t: t.name in ("strong", "b") or (t.name == "span" and "bold" in (t.get("style") or "")))
        if not bold:
            continue
        name = clean_text(bold.get_text(" "))
        if not name or _STOP.match(name) or name.endswith(":"):
            continue
        desc_parts = []
        for node in bold.next_siblings:
            text = clean_text(node.get_text(" ") if isinstance(node, Tag) else str(node))
            if isinstance(node, Tag) and node.name in ("strong", "b") and _STOP.match(text):
                break
            if text and not _STOP.match(text):
                desc_parts.append(text)
        desc = clean_text(" ".join(desc_parts))
        if len(desc) < 20:
            continue  # not a club paragraph
        website = instagram = None
        for a in p.find_all("a", href=True):
            href = a["href"].strip()
            if not href.startswith("http"):
                continue  # mailto:, constitution PDFs
            if is_instagram(href):
                instagram = instagram or normalize_instagram(href)
            elif "facebook.com" not in href and "website" in a.get_text(" ").lower():
                website = website or strip_tracking(href)
        if name in seen:
            continue
        seen.add(name)
        cat = cats.get(_norm(name))
        out.append({
            "key": name,
            "name": name,
            "description": desc,
            "listing_url": URL,
            "website": website,
            "instagram": instagram,
            "categories": [cat] if cat else [],
            "updated_at": None,
            "kind": "rec-club",
        })
    # The page has copy-paste errors (Table Tennis reuses Women's Football's text). A
    # description shared by several clubs stays only on the clubs whose name it mentions.
    by_desc: dict[str, list[dict]] = {}
    for r in out:
        by_desc.setdefault(r["description"], []).append(r)
    for desc, recs in by_desc.items():
        if len(recs) > 1:
            for r in recs:
                words = [w for w in re.findall(r"[a-z]{4,}", r["name"].lower()) if w not in {"club", "queen", "team"}]
                if not any(w in desc.lower() for w in words):
                    r["description"] = ""
    return out
