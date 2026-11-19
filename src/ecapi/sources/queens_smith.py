"""Smith School of Business: Commerce Society (ComSoc) clubs, conferences and committees.

The BCom "life outside class" page lists every ComSoc group in a table, with one row
per category. Names only, no descriptions or links.
"""

from __future__ import annotations

from typing import Any

from bs4 import BeautifulSoup

from ..http import PoliteClient
from ..text import clean_text

SOURCE_ID = "queens-comsoc"
SOURCE_NAME = "Smith School of Business: Commerce Society (ComSoc)"
URL = "https://smith.queensu.ca/bcom/experience/life-outside-class.php"


def fetch(client: PoliteClient) -> dict[str, Any]:
    return {"html": client.get(URL).text, "via": "live", "origin_url": URL}


def parse(raw: dict[str, Any]) -> list[dict[str, Any]]:
    soup = BeautifulSoup(raw["html"], "html.parser")
    out = []
    for row in soup.find_all("tr"):
        th, td = row.find("th"), row.find("td")
        if not th or not td:
            continue
        category = clean_text(th.get_text(" "))
        for li in td.find_all("li"):
            name = clean_text(li.get_text(" "))
            if not name:
                continue
            out.append({
                "key": name,
                "name": name,
                "description": "",
                "listing_url": URL,
                "website": None,
                "instagram": None,
                "categories": [category],
                "updated_at": None,
                "kind": category,
            })
    return out
