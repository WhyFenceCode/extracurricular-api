"""COMPSA (School of Computing) Computing Clubs Roundtable directory.

compsa.ca/ccr loads its club directory and open positions from its own JSON API:
``/api/ccr/clubs`` and ``/api/ccr/openings``.
"""

from __future__ import annotations

from typing import Any

from ..http import PoliteClient
from ..text import clean_text, is_instagram, normalize_instagram, strip_tracking

SOURCE_ID = "queens-compsa"
SOURCE_NAME = "COMPSA Computing Clubs Roundtable"
BASE = "https://compsa.ca"
LISTING = f"{BASE}/ccr"


def fetch(client: PoliteClient) -> dict[str, Any]:
    clubs = client.get(f"{BASE}/api/ccr/clubs").json()
    openings = client.get(f"{BASE}/api/ccr/openings").json()
    for name, payload in (("clubs", clubs), ("openings", openings)):
        if not isinstance(payload, dict) or not payload.get("success") or not isinstance(payload.get("data"), list):
            raise ValueError(f"unexpected COMPSA {name} payload")
    return {"clubs": clubs["data"], "openings": openings["data"], "via": "live", "origin_url": LISTING}


def _url(v: Any) -> str | None:
    if not isinstance(v, str) or not v.strip().startswith("http"):
        return None  # e.g. "[PLACEHOLDER URL]"
    return strip_tracking(v)


def parse(raw: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for c in raw["clubs"]:
        ig = _url(c.get("instagram"))
        out.append({
            "key": c["id"],
            "name": clean_text(c["name"]),
            "description": clean_text(c.get("description") or ""),
            "listing_url": LISTING,
            "website": _url(c.get("website_url")),
            "instagram": normalize_instagram(ig) if ig and is_instagram(ig) else None,
            "categories": [],
            "updated_at": None,
            "kind": "computing-club",
        })
    return out


def openings_for(raw: dict[str, Any], club: dict[str, Any]) -> list[dict[str, Any]]:
    """Openings that belong to a club (matched by club id or exact name)."""
    hits = []
    for o in raw.get("openings", []):
        cid = o.get("club_id") or (o.get("club") or {}).get("id") if isinstance(o.get("club"), dict) else o.get("club_id")
        cname = o.get("club_name") or (o.get("club") if isinstance(o.get("club"), str) else None)
        if cid == club["key"] or (cname and clean_text(cname).lower() == club["name"].lower()):
            hits.append({"name": clean_text(o.get("title") or o.get("role") or o.get("name") or "opening"),
                         "url": _url(o.get("url") or o.get("application_url") or o.get("link")) or LISTING})
    return hits
