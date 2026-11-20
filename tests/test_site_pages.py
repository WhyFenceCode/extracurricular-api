import re
from pathlib import Path

import pytest

from ecapi import build
from ecapi.schools import queens

STATIC = Path(build.__file__).parent / "static"
# The privacy page promises no third-party requests. Only these off-site *links* are allowed
# (plain <a href> the user clicks, never loaded automatically).
ALLOWED_LINKS = {"https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement"}


@pytest.fixture
def site(tmp_path, snapshots):
    items = queens.build_items(snapshots, {})
    build.clean(tmp_path)
    info = build.build_school(tmp_path, queens.SCHOOL_INFO, items, [], "2026-11-19T00:00:00+00:00")
    build.build_root(tmp_path, [info])
    (tmp_path / "versions.json").write_text("{}", encoding="utf-8")  # normally written by versions.publish
    return tmp_path


def test_privacy_page_ships_and_is_linked(site):
    assert (site / "privacy.html").exists()
    assert 'href="privacy.html"' in (site / "index.html").read_text(encoding="utf-8")


@pytest.mark.parametrize("page", ["index.html", "privacy.html"])
def test_pages_load_nothing_from_other_sites(page):
    html = (STATIC / page).read_text(encoding="utf-8")
    # anything the browser fetches on its own: scripts, styles, images, fonts, iframes
    loaded = re.findall(r'<(?:script|img|iframe|link|source|video|audio)[^>]+(?:src|href)="([^"]+)"', html, re.I)
    loaded += re.findall(r"url\(\s*['\"]?(https?:[^'\")]+)", html, re.I)
    loaded += re.findall(r"@import\s+['\"]?(https?:[^'\";]+)", html, re.I)
    assert [u for u in loaded if re.match(r"(?:https?:)?//", u)] == []
    for js_url in re.findall(r"fetch\(\s*[`'\"](https?:[^`'\"]+)", html):
        pytest.fail(f"{page} fetches {js_url}")
    scripts = " ".join(re.findall(r"<script[^>]*>(.*?)</script>", html, re.S | re.I))
    for flag in ("document.cookie", "localStorage", "sessionStorage", "indexedDB", "navigator.sendBeacon",
                 "gtag(", "dataLayer", "XMLHttpRequest", "WebSocket"):
        assert flag not in scripts, f"{page} script uses {flag}"


@pytest.mark.parametrize("page", ["index.html", "privacy.html"])
def test_page_links_resolve(site, page):
    html = (site / page).read_text(encoding="utf-8")
    for href in re.findall(r'href="([^"#][^"]*)"', html):
        if href.startswith(("http://", "https://")):
            assert href in ALLOWED_LINKS, f"{page}: unexpected external link {href}"
            continue
        target = site / (href.rstrip("/") or ".")
        if href in ("./", "."):
            target = site / "index.html"
        assert target.exists(), f"{page}: broken link {href}"


def _plain(s: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", s).split())


def test_disclaimer_everywhere(site):
    """Not-affiliated notice: one text (build.DISCLAIMER), shown in every public place."""
    import json

    text = build.DISCLAIMER
    for page in ("index.html", "privacy.html"):
        assert text in _plain((site / page).read_text(encoding="utf-8")), f"{page} lacks the disclaimer"
    assert json.loads((site / "v1/index.json").read_text(encoding="utf-8"))["disclaimer"] == text
    assert json.loads((site / "v1/queens/info.json").read_text(encoding="utf-8"))["disclaimer"] == text
    root = Path(build.__file__).parents[2]
    assert text in " ".join((root / "README.md").read_text(encoding="utf-8").split())
    for md in ("docs/README.md", "docs/schools/queens.md"):
        assert text in (root / md).read_text(encoding="utf-8"), md


def test_exclude_removes_item_and_tolerates_vanished_ids(snapshots):
    ids = {i.id for i in queens.build_items(snapshots, {})}
    assert "ams-debate-union" in ids
    items = queens.build_items(snapshots, {
        "ams-debate-union": {"exclude": True, "note": "removal request"},
        "ams-long-gone-club": {"exclude": True},  # no longer in any source: fine
    })
    assert "ams-debate-union" not in {i.id for i in items}
    assert len(items) == len(ids) - 1
    with pytest.raises(ValueError, match="only have 'exclude'"):
        queens.build_items(snapshots, {"ams-debate-union": {"exclude": True, "name": "x"}})
