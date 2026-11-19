"""Queen's Engineering Society: design teams, EngSoc clubs and discipline clubs.

The directory pages are WordPress/Elementor loop grids. If the live site can't be
reached (its DNS was failing when this was written), we fall back to the most recent
Internet Archive capture of the same page and record that in the snapshot.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import httpx
from bs4 import BeautifulSoup

from ..http import PoliteClient, RobotsDisallowed
from ..text import clean_text, is_instagram, normalize_instagram, strip_tracking

SOURCE_ID = "queens-engsoc"
SOURCE_NAME = "Queen's Engineering Society"
BASE = "https://www.engsoc.queensu.ca"
PAGES = {
    "design-team": f"{BASE}/get-involved/design-teams/",
    "engsoc-club": f"{BASE}/get-involved/clubs/",
    "discipline-club": f"{BASE}/get-involved/discipline-clubs/",
}


def _wayback(url: str) -> str:
    return f"https://web.archive.org/web/{dt.date.today():%Y%m%d}id_/{url}"


def fetch(client: PoliteClient) -> dict[str, Any]:
    pages = {}
    for kind, url in PAGES.items():
        try:
            r = client.get(url)
            pages[kind] = {"html": r.text, "via": "live", "url": url}
        except (httpx.HTTPError, RobotsDisallowed) as live_err:
            r = client.get(_wayback(url))  # raises if the archive fails too
            pages[kind] = {
                "html": r.text,
                "via": "wayback",
                "url": url,
                "archived_at": r.headers.get("Memento-Datetime"),
                "live_error": str(live_err)[:200],
            }
    return {"pages": pages, "via": ",".join(sorted({p["via"] for p in pages.values()})), "origin_url": BASE}


def parse_page(html: str, kind: str, listing_url: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for card in soup.select("div.e-loop-item"):
        h = card.select_one(".elementor-heading-title")
        if not h:
            continue
        name = clean_text(h.get_text())
        excerpt = card.select_one(".elementor-widget-theme-post-excerpt .elementor-widget-container")
        website = instagram = None
        for a in card.select("a.elementor-social-icon[href]"):
            href = a["href"].strip()
            if is_instagram(href):
                instagram = instagram or normalize_instagram(href)
            elif "elementor-social-icon-globe" in a.get("class", []) and "@" not in href:
                website = website or strip_tracking(href)
        out.append(
            {
                "key": name,
                "name": name,
                "description": clean_text(excerpt.get_text(" ")) if excerpt else "",
                "listing_url": listing_url,
                "website": website,
                "instagram": instagram,
                "categories": [],
                "updated_at": None,
                "kind": kind,
            }
        )
    return out


def parse(raw: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for kind, page in raw["pages"].items():
        out.extend(parse_page(page["html"], kind, page["url"]))
    return out
