"""Queen's AMS (Alma Mater Society) club directory.

Uses the site's public WordPress REST API (custom post type ``club`` with the
``club-categories`` taxonomy) -- the same data behind https://www.myams.org/clubs/club-directory/.
robots.txt asks for a 600 s crawl-delay; PoliteClient honours it, which is why a full
scrape (5 requests) takes ~40 minutes. That's fine for a weekly GitHub Action.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

from ..http import PoliteClient
from ..text import clean_text, html_to_text, is_instagram, normalize_instagram, strip_tracking

SOURCE_ID = "queens-ams"
SOURCE_NAME = "Queen's AMS Club Directory"
BASE = "https://www.myams.org"
DIRECTORY_URL = f"{BASE}/clubs/club-directory/"
_LINK_WORDS = {"learn more", "connect with us", "website", "linktree", "instagram", "click here"}


def fetch(client: PoliteClient) -> dict[str, Any]:
    cats = client.get(f"{BASE}/wp-json/wp/v2/club-categories?per_page=100&_fields=id,name,slug").json()
    clubs: list[dict] = []
    page, total_pages = 1, 1
    while page <= total_pages:
        r = client.get(
            f"{BASE}/wp-json/wp/v2/club?per_page=100&page={page}"
            "&_fields=id,slug,link,title,content,club-categories,modified"
        )
        total_pages = int(r.headers.get("X-WP-TotalPages", "1"))
        clubs.extend(r.json())
        page += 1
    return {"categories": cats, "clubs": clubs, "via": "live", "origin_url": DIRECTORY_URL}


def parse(raw: dict[str, Any]) -> list[dict[str, Any]]:
    cat_names = {c["id"]: clean_text(c["name"]) for c in raw["categories"]}
    out = []
    for c in raw["clubs"]:
        content = c.get("content", {}).get("rendered", "")
        soup = BeautifulSoup(content, "html.parser")
        website = instagram = None
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            host = urlsplit(href).netloc
            if not href.startswith("http") or host.endswith("myams.org"):
                continue  # attachment/image links back into the AMS site
            if is_instagram(href):
                instagram = instagram or normalize_instagram(href)
            else:
                website = website or strip_tracking(href)
        # Drop "Learn More" / "Connect with us" link text from the description.
        for a in soup.find_all("a"):
            if clean_text(a.get_text()).lower() in _LINK_WORDS:
                a.decompose()
        out.append(
            {
                "key": c["slug"],
                "name": clean_text(c["title"]["rendered"]),
                "description": html_to_text(str(soup)),
                "listing_url": c["link"],
                "website": website,
                "instagram": instagram,
                "categories": sorted({cat_names[i] for i in c.get("club-categories", []) if i in cat_names}),
                "updated_at": c.get("modified"),
                "kind": "ams-club",
            }
        )
    return out
