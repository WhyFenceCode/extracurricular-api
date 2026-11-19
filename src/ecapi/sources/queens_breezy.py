"""EngSoc's hiring portal on Breezy HR. Design teams and EngSoc teams post their
recruitment calls here, so an active posting is our signal that applications are open.

Breezy exposes public postings as JSON at ``https://<company>.breezy.hr/json``.
"""

from __future__ import annotations

from typing import Any

from ..http import PoliteClient
from ..text import clean_text

SOURCE_ID = "queens-engsoc-breezy"
SOURCE_NAME = "Queen's EngSoc hiring portal (Breezy HR)"
PORTAL = "https://the-engineering-society-of-queen-s-university.breezy.hr"


def fetch(client: PoliteClient) -> dict[str, Any]:
    postings = client.get(f"{PORTAL}/json").json()
    if not isinstance(postings, list):
        raise ValueError(f"unexpected Breezy payload: {type(postings).__name__}")
    return {"postings": postings, "via": "live", "origin_url": PORTAL}


def parse(raw: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for p in raw["postings"]:
        dept = p.get("department")
        if isinstance(dept, dict):
            dept = dept.get("name")
        out.append(
            {
                "name": clean_text(p.get("name", "")),
                "department": clean_text(dept) if dept else None,
                "url": p.get("url") or f"{PORTAL}/p/{p.get('friendly_id', '')}",
                "published": p.get("published_date"),
            }
        )
    return out
