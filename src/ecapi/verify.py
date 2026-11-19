"""Checks a built site end-to-end, reading only the generated files.

Filtered responses are recomputed here with a separate, straightforward predicate
(not the builder's bucketing code), so a bug in one shows up as a mismatch.
"""

from __future__ import annotations

import itertools
import json
from pathlib import Path
from typing import Any

from .schema import API_VERSION, Item

V = f"v{API_VERSION}"
ENVELOPE = ["api_version", "deprecated", "school", "data_as_of", "endpoint"]

DIMS = ["faculty", "subfaculty", "type", "app", "first"]


def _strip(value: str, prefix: str) -> str:
    assert value.startswith(prefix + "-"), f"{value!r} should start with {prefix}-"
    return value[len(prefix) + 1:]


def _load(p: Path) -> Any:
    return json.loads(p.read_text(encoding="utf-8"))


def matches(item: dict, q: dict[str, str]) -> bool:
    fac, sub = _strip(q["faculty"], "fac"), _strip(q["subfaculty"], "sub")
    typ, app, first = _strip(q["type"], "type"), _strip(q["app"], "app"), _strip(q["first"], "first")
    if fac != "any" and item["faculty"] != fac:
        return False
    if sub != "any" and item["subfaculty"] != sub:
        return False
    if typ != "any" and item["type"] != typ:
        return False
    status = {True: "open", False: "closed", None: "unknown"}[item["applications_open"]]
    if app != "any" and status != app:
        return False
    fy = item["eligibility"]["first_year"]
    if first == "friendly":
        if fy not in ("friendly", "focused"):
            return False
    elif first == "unknown":
        if fy is not None:
            return False
    elif first != "any" and fy != first:
        return False
    return True


def verify_school(site: Path, school: str, min_per_source: dict[str, int] | None = None) -> list[str]:
    errors: list[str] = []
    root = site / V / school
    index = _load(root / "all.json")
    meta = _load(root / "info.json")
    items = index["items"]

    if index["count"] != len(items):
        errors.append(f"all.json count {index['count']} != {len(items)} items")
    ids = [i["id"] for i in items]
    if len(set(ids)) != len(ids):
        errors.append("duplicate ids in all.json")
    for it in items:
        try:
            Item.model_validate(it)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{it.get('id')}: schema: {e}")
        if it["school"] != school or it["api_version"] != index["api_version"]:
            errors.append(f"{it['id']}: wrong school/api_version")

    # per-item endpoints
    item_files = {p.stem for p in (root / "item").glob("*.json")}
    if item_files != set(ids):
        errors.append(f"item files mismatch: missing={sorted(set(ids) - item_files)[:5]} extra={sorted(item_files - set(ids))[:5]}")
    for it in items:
        p = root / "item" / f"{it['id']}.json"
        if p.exists() and _load(p)["item"] != it:
            errors.append(f"{it['id']}: item file differs from all.json")

    # every filter combination exists and is exactly right
    f = meta["filters"]
    expected_subs: dict[str, set[str]] = {"fac-any": {"sub-any"}}
    # declared faculties/subfaculties always have endpoints; so does anything an item uses
    for fac, finfo in meta["faculties"].items():
        expected_subs[f"fac-{fac}"] = {"sub-any"} | {f"sub-{s}" for s in finfo.get("subfaculties", {})}
    for it in items:
        expected_subs.setdefault(f"fac-{it['faculty']}", {"sub-any"})
        if it["subfaculty"]:
            expected_subs[f"fac-{it['faculty']}"].add(f"sub-{it['subfaculty']}")
    if set(f["faculty"]["values"]) != set(expected_subs):
        errors.append("info.json faculty values do not match declared + used faculties")
    if {k: set(v) for k, v in f["subfaculty"]["by_faculty"].items()} != expected_subs:
        errors.append("info.json subfaculty tree does not match items")
    n = 0
    for fac, subs in expected_subs.items():
        for combo in itertools.product(sorted(subs), *(f[d]["values"] for d in DIMS[2:])):
            q = dict(zip(DIMS, (fac, *combo)))
            p = root / "filter" / fac / q["subfaculty"] / q["type"] / q["app"] / f"{q['first']}.json"
            if not p.exists():
                errors.append(f"missing filter file {p.relative_to(site)}")
                continue
            got = _load(p)
            expected = [it for it in items if matches(it, q)]
            if got["query"] != q:
                errors.append(f"{p.relative_to(site)}: query echo {got['query']} != {q}")
            if got["count"] != len(got["items"]) or got["items"] != expected:
                errors.append(f"{p.relative_to(site)}: expected {len(expected)} items, got {got['count']}")
            n += 1
    if n != meta["filter_files"]:
        errors.append(f"meta.filter_files={meta['filter_files']} but checked {n}")
    on_disk = sum(1 for _ in (root / "filter").rglob("*.json"))
    if on_disk != n:
        errors.append(f"{on_disk} filter files on disk, expected {n}")

    # tags
    all_tags = sorted({t for it in items for t in it["tags"]})
    tag_list = _load(root / "tags.json")["tags"]
    if sorted(tag_list) != all_tags:
        errors.append("tags.json does not match item tags")
    for t in all_tags:
        if tag_list.get(t) != sum(1 for it in items if t in it["tags"]):
            errors.append(f"tags.json count for {t} is wrong")
        got = _load(root / "tag" / f"{t}.json")
        if got["items"] != [it for it in items if t in it["tags"]]:
            errors.append(f"tag {t}: wrong items")

    # every response carries the full envelope, and the current version is never deprecated
    for p in [root / "all.json", root / "info.json", root / "tags.json",
              next(iter((root / "item").glob("*.json")), None),
              root / "filter" / "fac-any" / "sub-any" / "type-any" / "app-any" / "first-any.json"]:
        if p is None:
            continue
        env = _load(p)
        missing = [k for k in ENVELOPE if k not in env]
        if missing:
            errors.append(f"{p.relative_to(site)}: envelope missing {missing}")
        if env.get("deprecated") is not False:
            errors.append(f"{p.relative_to(site)}: current version response must have deprecated=false")

    # unfiltered sanity: the 'any' file equals the index
    every = _load(root / "filter" / "fac-any" / "sub-any" / "type-any" / "app-any" / "first-any.json")
    if every["items"] != items:
        errors.append("filter/fac-any/sub-any/type-any/app-any/first-any.json != all.json")

    # scraper health: a source that suddenly yields far fewer items is probably broken
    for src, minimum in (min_per_source or {}).items():
        # merged duplicates still count for every directory that listed them
        c = sum(1 for it in items if it["source"]["id"] == src
                or any(x["source"]["id"] == src for x in it.get("also_listed_in", [])))
        if c < minimum:
            errors.append(f"source {src}: only {c} items (expected >= {minimum}); scraper may be broken")
    return errors


def verify_root(site: Path) -> list[str]:
    errors = []
    schools = _load(site / V / "schools.json")
    guide = _load(site / V / "index.json")
    if sorted(s["id"] for s in schools["schools"]) != sorted(guide["schools"]):
        errors.append(f"{V}/index.json and {V}/schools.json list different schools")
    for s in schools["schools"]:
        if not (site / s["info"]).exists():
            errors.append(f"school {s['id']}: info.json missing")
    # every example URL in the guide must resolve
    for ep in guide["endpoints"].values():
        if "example" in ep and not (site / ep["example"]).exists():
            errors.append(f"guide example does not exist: {ep['example']}")
    return errors


def verify_versions(site: Path, registry: dict[str, dict]) -> list[str]:
    """versions.json matches the registry; every file of a deprecated version is stamped."""
    errors: list[str] = []
    p = site / "versions.json"
    if not p.exists():
        return ["versions.json missing from site root"]
    listing = _load(p)
    if listing.get("current") != V:
        errors.append(f"versions.json current={listing.get('current')} but code is {V}")
    if set(listing.get("versions", {})) != set(registry):
        errors.append("versions.json and api-versions.json list different versions")
    for v, e in registry.items():
        vdir = site / v
        if not vdir.is_dir():
            errors.append(f"{v} is registered but not in the site")
            continue
        if e.get("status") != "deprecated":
            continue
        bad = 0
        for f in vdir.rglob("*.json"):
            obj = _load(f)
            d = obj.get("deprecation") if isinstance(obj, dict) else None
            if not (isinstance(obj, dict) and obj.get("deprecated") is True and d and d.get("successor")):
                bad += 1
        if bad:
            errors.append(f"{v}: {bad} file(s) not stamped deprecated")
    return errors
