"""Generates the static JSON API (GitHub Pages can only serve files, so every
filter combination is pre-computed).

Layout (all under ``site/``):

  v{N}/index.json                    API guide: every endpoint, with examples
  v{N}/schools.json                  schools this API covers
  v{N}/{school}/info.json            faculties, sources and freshness, valid filter values with counts
  v{N}/{school}/all.json             every activity at the school
  v{N}/{school}/item/{id}.json       one activity
  v{N}/{school}/tags.json            every tag, with counts
  v{N}/{school}/tag/{tag}.json       activities with one tag
  v{N}/{school}/filter/fac-{faculty}/sub-{subfaculty}/type-{type}/app-{status}/first-{status}.json

Every filter segment names its dimension, so a URL reads on its own:

  filter/fac-engineering/sub-any/type-design-team/app-open/first-friendly.json

``-any`` skips a dimension. ``sub-*`` values other than ``sub-any`` only exist under
their own faculty (``fac-engineering/sub-civil-engineering``), never under ``fac-any``.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from .schema import API_VERSION, Item, ItemType

V = f"v{API_VERSION}"  # every path of the current API version lives under this prefix

DIMENSIONS = ["faculty", "subfaculty", "type", "app", "first"]
APP_VALUES = ["app-any", "app-open", "app-rolling", "app-closed", "app-unknown"]
FIRST_VALUES = ["first-any", "first-focused", "first-friendly", "first-no", "first-unknown"]
TYPE_VALUES = ["type-any"] + [f"type-{t.value}" for t in ItemType]
FILTER_TEMPLATE = V + "/{school}/filter/fac-{faculty}/sub-{subfaculty}/type-{type}/app-{app}/first-{first}.json"

VALUE_DOCS = {
    "app-open": "applications are being accepted (includes app-rolling)",
    "app-rolling": "always open: join or drop by any time, no application window",
    "app-closed": "applications are not being accepted right now",
    "app-unknown": "the source doesn't say",
    "first-focused": "aimed specifically at first-year students",
    "first-friendly": "first-years can join (includes first-focused)",
    "first-no": "not open to first-years",
    "first-unknown": "the source doesn't say",
    "type-club": "student club",
    "type-team": "sports or performance team",
    "type-design-team": "engineering design team building a project for competition",
    "type-discipline-club": "club for one engineering discipline",
    "type-committee": "student-government committee or operational team",
    "type-conference": "student-run conference",
    "type-competition": "student-run competition",
}


def endpoint_guide(school: str = "{school}") -> dict[str, dict[str, str]]:
    ex = "queens" if school == "{school}" else school
    return {
        "schools": {"path": f"{V}/schools.json", "returns": "the schools this API covers"},
        "info": {"path": f"{V}/{school}/info.json",
                 "returns": "faculties and subfaculties, data sources and freshness, every valid filter value with counts",
                 "example": f"{V}/{ex}/info.json"},
        "all": {"path": f"{V}/{school}/all.json", "returns": "every activity at the school",
                "example": f"{V}/{ex}/all.json"},
        "item": {"path": f"{V}/{school}/item/{{id}}.json", "returns": "one activity, by id",
                 "example": f"{V}/{ex}/item/engsoc-qset.json"},
        "filter": {"path": FILTER_TEMPLATE.replace("{school}", school),
                   "returns": "activities matching all five filters; use -any to skip one",
                   "example": f"{V}/{ex}/filter/fac-engineering/sub-any/type-design-team/app-open/first-friendly.json"},
        "tags": {"path": f"{V}/{school}/tags.json", "returns": "every tag, with how many activities have it",
                 "example": f"{V}/{ex}/tags.json"},
        "tag": {"path": f"{V}/{school}/tag/{{tag}}.json", "returns": "activities with one tag",
                "example": f"{V}/{ex}/tag/robotics.json"},
    }


def app_values(open_: bool | None, deadline: str | None) -> set[str]:
    if open_ is None:
        return {"app-unknown"}
    if not open_:
        return {"app-closed"}
    return {"app-open", "app-rolling"} if deadline == "rolling" else {"app-open"}  # rolling implies open


def first_values(first_year: str | None) -> set[str]:
    if first_year is None:
        return {"first-unknown"}
    if first_year == "focused":
        return {"first-focused", "first-friendly"}  # focused implies friendly
    return {f"first-{first_year}"}


def item_keys(item: Item) -> dict[str, set[str]]:
    """The filter values an item belongs to, per dimension (``-any`` always included)."""
    return {
        "faculty": {"fac-any", f"fac-{item.faculty}"},
        "subfaculty": {"sub-any"} | ({f"sub-{item.subfaculty}"} if item.subfaculty else set()),
        "type": {"type-any", f"type-{item.type.value}"},
        "app": {"app-any"} | app_values(item.applications_open, item.application_deadline),
        "first": {"first-any"} | first_values(item.eligibility.first_year),
    }


def faculty_tree(items: list[Item], faculties: dict[str, dict]) -> dict[str, list[str]]:
    """fac-* value -> the sub-* values valid beneath it. Declared faculties and subfaculties
    always get endpoints (possibly empty), so URLs stay stable as sources come and go."""
    tree: dict[str, set[str]] = {"fac-any": {"sub-any"}}
    for f, info in faculties.items():
        tree[f"fac-{f}"] = {"sub-any"} | {f"sub-{s}" for s in info.get("subfaculties", {})}
    for i in items:
        tree.setdefault(f"fac-{i.faculty}", {"sub-any"})
        if i.subfaculty:
            tree[f"fac-{i.faculty}"].add(f"sub-{i.subfaculty}")

    def sub_order(v: str):
        return (v != "sub-any", v)

    return {f: sorted(subs, key=sub_order) for f, subs in sorted(tree.items(), key=lambda kv: (kv[0] != "fac-any", kv[0]))}


def combinations(tree: dict[str, list[str]]):
    for fac, subs in tree.items():
        for sub in subs:
            for typ in TYPE_VALUES:
                for app in APP_VALUES:
                    for first in FIRST_VALUES:
                        yield {"faculty": fac, "subfaculty": sub, "type": typ, "app": app, "first": first}


def filter_path(q: dict[str, str]) -> str:
    return "/".join(q[d] for d in DIMENSIONS) + ".json"


def _write(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1, sort_keys=False) + "\n", encoding="utf-8")


def _envelope(school: str, as_of: str, **kw) -> dict[str, Any]:
    # "deprecated" is on every response so clients can check it uniformly; frozen old
    # versions have it set to true plus a "deprecation" block (see versions.py).
    return {"api_version": API_VERSION, "deprecated": False, "school": school, "data_as_of": as_of, **kw}


def build_school(out: Path, school_info: dict, items: list[Item], sources_meta: list[dict],
                 as_of: str) -> dict[str, Any]:
    school = school_info["id"]
    root = out / V / school
    dumped = {i.id: i.model_dump(mode="json") for i in items}
    keys = {i.id: item_keys(i) for i in items}
    faculties = school_info.get("faculties", {})
    tree = faculty_tree(items, faculties)

    _write(root / "all.json", _envelope(school, as_of, endpoint="all", count=len(items), items=list(dumped.values())))

    for i in items:
        _write(root / "item" / f"{i.id}.json", _envelope(school, as_of, endpoint="item", item=dumped[i.id]))

    files = 0
    for q in combinations(tree):
        match = [dumped[i.id] for i in items if all(q[d] in keys[i.id][d] for d in DIMENSIONS)]
        _write(root / "filter" / filter_path(q),
               _envelope(school, as_of, endpoint="filter", query=q, count=len(match), items=match))
        files += 1

    tags: dict[str, list[str]] = {}
    for i in items:
        for t in i.tags:
            tags.setdefault(t, []).append(i.id)
    for t, ids in tags.items():
        _write(root / "tag" / f"{t}.json", _envelope(school, as_of, endpoint="tag", query={"tag": t},
                                                     count=len(ids), items=[dumped[x] for x in ids]))
    tag_counts = dict(sorted((t, len(ids)) for t, ids in tags.items()))
    _write(root / "tags.json", _envelope(school, as_of, endpoint="tags", count=len(tag_counts), tags=tag_counts))

    def counts(d: str) -> dict[str, int]:
        c: dict[str, int] = {}
        for i in items:
            for v in keys[i.id][d]:
                if not v.endswith("-any"):
                    c[v] = c.get(v, 0) + 1
        return dict(sorted(c.items()))

    fac_counts = counts("faculty")
    faculty_info = {
        f: {**info, "items": fac_counts.get(f"fac-{f}", 0),
            "filter": f"{V}/{school}/filter/fac-{f}/sub-any/type-any/app-any/first-any.json"}
        for f, info in faculties.items()
    }
    all_subs = sorted({s for subs in tree.values() for s in subs}, key=lambda v: (v != "sub-any", v))
    info = _envelope(
        school, as_of,
        endpoint="info",
        school_info={k: v for k, v in school_info.items() if k != "faculties"},
        count=len(items),
        faculties=faculty_info,
        sources=sources_meta,
        filters={
            "faculty": {"values": list(tree), "counts": fac_counts},
            "subfaculty": {"values": all_subs, "by_faculty": tree, "counts": counts("subfaculty")},
            "type": {"values": TYPE_VALUES, "counts": counts("type"),
                     "meaning": {v: VALUE_DOCS[v] for v in TYPE_VALUES if v in VALUE_DOCS}},
            "app": {"values": APP_VALUES, "counts": counts("app"),
                    "meaning": {v: VALUE_DOCS[v] for v in APP_VALUES if v in VALUE_DOCS}},
            "first": {"values": FIRST_VALUES, "counts": counts("first"),
                      "meaning": {v: VALUE_DOCS[v] for v in FIRST_VALUES if v in VALUE_DOCS}},
        },
        endpoints=endpoint_guide(school),
        numeric_fields={
            "time_commitment.hours_per_week_min": "number|null",
            "time_commitment.hours_per_week_max": "number|null",
            "meetings.per_week": "number|null (1 = weekly, 0.5 = biweekly, 2 = twice a week, 0.25 = monthly)",
            "eligibility.years": "int[]|null",
        },
        filter_files=files,
    )
    _write(root / "info.json", info)
    return {"id": school, "name": school_info["name"], "count": len(items), "info": f"{V}/{school}/info.json",
            "data_as_of": as_of}


def build_root(out: Path, schools: list[dict]) -> None:
    as_of = max((s["data_as_of"] for s in schools if s.get("data_as_of")), default=None)
    _write(out / V / "schools.json", {"api_version": API_VERSION, "deprecated": False, "data_as_of": as_of,
                                      "endpoint": "schools", "count": len(schools), "schools": schools})
    _write(out / V / "index.json", {
        "api_version": API_VERSION,
        "deprecated": False,
        "endpoint": "index",
        "versions": "versions.json",
        "about": "Static JSON API of university extracurriculars. All paths are relative to this site's root.",
        "schools": [s["id"] for s in schools],
        "endpoints": endpoint_guide(),
        "filter_segments": {
            "faculty": f"fac-any | fac-<faculty>  (see {V}/{{school}}/info.json)",
            "subfaculty": "sub-any | sub-<subfaculty>  (only under its own faculty)",
            "type": TYPE_VALUES,
            "app": APP_VALUES,
            "first": FIRST_VALUES,
        },
        "meaning": VALUE_DOCS,
        "docs": "index.html",
    })
    (out / ".nojekyll").write_text("", encoding="utf-8")
    _write(out / "404.json", {"error": "not_found", "hint": f"see {V}/index.json for valid endpoints, or versions.json for all API versions"})
    static = Path(__file__).parent / "static"
    for f in static.glob("*"):
        shutil.copy2(f, out / f.name)


def clean(out: Path) -> None:
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
