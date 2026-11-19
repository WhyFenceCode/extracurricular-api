"""Queen's University (Kingston, ON): turns source snapshots into API items."""

from __future__ import annotations

import re
from typing import Any

from .. import infer
from ..schema import (
    API_VERSION, Eligibility, Item, ItemType, Links, Listing, Meetings, Method, Provenance, SourceRef, TimeCommitment,
)
from ..sources import (
    queens_ams, queens_breezy, queens_compsa, queens_engsoc, queens_hss, queens_rec, queens_smith,
)
from ..text import slugify

SCHOOL = "queens"

# EngSoc discipline clubs -> engineering programme (subfaculty)
DISCIPLINE = {
    "apple dsc": "mathematics-engineering",
    "chemengchem dsc": "chemical-engineering",
    "civil dsc": "civil-engineering",
    "ece club": "electrical-computer-engineering",
    "mech dsc": "mechanical-engineering",
    "miller club": "geological-engineering",
    "mining society": "mining-engineering",
    "mre dsc": "mechatronics-robotics-engineering",
    "physics dsc": "engineering-physics",
}
_DISCIPLINE_NAMES = {
    "mathematics-engineering": "Mathematics & Engineering (Apple DSC)",
    "chemical-engineering": "Chemical Engineering (ChemEngChem DSC)",
    "civil-engineering": "Civil Engineering (Civil DSC)",
    "electrical-computer-engineering": "Electrical & Computer Engineering (ECE Club)",
    "mechanical-engineering": "Mechanical Engineering (Mech DSC)",
    "geological-engineering": "Geological Engineering (Miller Club)",
    "mining-engineering": "Mining Engineering (Mining Society)",
    "mechatronics-robotics-engineering": "Mechatronics & Robotics Engineering (MRE DSC)",
    "engineering-physics": "Engineering Physics (Physics DSC)",
}

# Every faculty gets endpoints, even before it has a source, so URLs are stable.
# "sources" lists where its data comes from; an empty list means no public directory found yet.
SCHOOL_INFO = {
    "id": SCHOOL,
    "name": "Queen's University",
    "location": "Kingston, Ontario, Canada",
    "faculties": {
        "general": {
            "name": "Any faculty",
            "description": "AMS-ratified clubs and Athletics & Recreation clubs, open to students from every faculty",
            "sources": [queens_ams.SOURCE_ID, queens_rec.SOURCE_ID],
            "subfaculties": {},
        },
        "arts-science": {
            "name": "Faculty of Arts and Science",
            "description": "ASUS does not publish a club directory; School of Computing clubs come from COMPSA",
            "sources": [queens_compsa.SOURCE_ID],
            "subfaculties": {"computing": "School of Computing (COMPSA Computing Clubs Roundtable)"},
        },
        "business": {
            "name": "Smith School of Business",
            "description": "Commerce Society (ComSoc) clubs, conferences, competitions and committees",
            "sources": [queens_smith.SOURCE_ID],
            "subfaculties": {"commerce": "Bachelor of Commerce (ComSoc)"},
        },
        "engineering": {
            "name": "Smith Engineering",
            "description": "Engineering Society design teams, clubs and discipline clubs",
            "sources": [queens_engsoc.SOURCE_ID, queens_breezy.SOURCE_ID],
            "subfaculties": _DISCIPLINE_NAMES,
        },
        "health-sciences": {
            "name": "Faculty of Health Sciences",
            "description": "Health Sciences Society (BHSc) ratified clubs; Nursing, Medicine and Rehab have no public directory yet",
            "sources": [queens_hss.SOURCE_ID],
            "subfaculties": {"bachelor-health-sciences": "Bachelor of Health Sciences (HSS)"},
        },
        "education": {"name": "Faculty of Education", "description": "No public club directory found yet",
                      "sources": [], "subfaculties": {}},
        "law": {"name": "Faculty of Law", "description": "No public club directory found yet",
                "sources": [], "subfaculties": {}},
        "graduate": {"name": "School of Graduate Studies and Postdoctoral Affairs",
                     "description": "No public club directory found yet", "sources": [], "subfaculties": {}},
    },
}
# Priority order: faculty-specific directories first, the general AMS directory last, so when
# one club is listed in two places the more specific listing wins the merge.
SOURCES = [queens_engsoc, queens_breezy, queens_compsa, queens_hss, queens_smith, queens_rec, queens_ams]

# EngSoc "clubs" page entries that are really EngSoc-run operational teams.
_COMMITTEE = re.compile(r"^(?:outreach|it operations|equity|communications|automation) teams?$|software development team", re.I)

# ComSoc table rows -> item type (anything else is a club)
COMSOC_TYPES = {
    "External: Conferences & Competitions": ItemType.conference,
    "External Competitions": ItemType.competition,
    "Executive Purview": ItemType.committee,
}

_ACRONYM = re.compile(r"\(([A-Za-z0-9]{2,8})\)")


def _acronym(name: str) -> str | None:
    m = _ACRONYM.search(name)
    return m.group(1).upper() if m else None


def _id(prefix: str, name: str) -> str:
    acr = _acronym(name)
    slug = (acr or slugify(name)).lower()
    return slug if slug.startswith(f"{prefix}-") else f"{prefix}-{slug}"


def _engsoc_id(name: str) -> str:
    return _id("engsoc", name)


def _match_postings(name: str, postings: list[dict]) -> list[dict]:
    """Postings whose title or department names this team (acronym or full name)."""
    acr = _acronym(name)
    bare = re.sub(r"\s*\([^)]*\)", "", name).replace("Queen's ", "").strip().lower()
    hits = []
    for p in postings:
        hay = f"{p['name']} {p.get('department') or ''}"
        if (acr and re.search(rf"\b{re.escape(acr)}\b", hay)) or (len(bare) > 4 and bare in hay.lower()):
            hits.append(p)
    return hits


def _src(mod, url: str) -> SourceRef:
    return SourceRef(id=mod.SOURCE_ID, name=mod.SOURCE_NAME, url=url)


def build_items(snapshots: dict[str, dict | None], overrides: dict[str, dict]) -> list[Item]:
    items: list[Item] = []

    def snap(mod):
        return snapshots.get(mod.SOURCE_ID)

    breezy = snap(queens_breezy)
    postings = queens_breezy.parse(breezy["raw"]) if breezy else None
    if not postings:
        # An empty portal can't distinguish "nobody is recruiting" from "the portal moved",
        # so it tells us nothing: leave applications_open unknown rather than claim False.
        postings = None

    if eng := snap(queens_engsoc):
        src = _src(queens_engsoc, queens_engsoc.BASE)
        for rec in queens_engsoc.parse(eng["raw"]):
            kind = rec["kind"]
            sub = None
            if kind == "design-team":
                typ = ItemType.design_team
            elif kind == "discipline-club":
                typ = ItemType.discipline_club
                sub = DISCIPLINE.get(rec["name"].lower())
            elif _COMMITTEE.search(rec["name"]):
                typ = ItemType.committee
            else:
                typ = ItemType.club
            recruiting = None
            if postings is not None and kind != "discipline-club":
                recruiting = _match_postings(rec["name"], postings)
            items.append(_item(rec, src, _engsoc_id(rec["name"]), typ, "engineering", sub, recruiting))

    if compsa := snap(queens_compsa):
        src = _src(queens_compsa, queens_compsa.LISTING)
        any_openings = bool(compsa["raw"].get("openings"))
        for rec in queens_compsa.parse(compsa["raw"]):
            # Same rule as Breezy: an empty openings board tells us nothing.
            openings = queens_compsa.openings_for(compsa["raw"], rec) if any_openings else None
            items.append(_item(rec, src, _id("compsa", rec["name"]), ItemType.club, "arts-science", "computing",
                               openings, posting_source="COMPSA CCR open positions"))

    if hss := snap(queens_hss):
        src = _src(queens_hss, queens_hss.URL)
        for rec in queens_hss.parse(hss["raw"]):
            items.append(_item(rec, src, _id("hss", rec["name"]), ItemType.club, "health-sciences",
                               "bachelor-health-sciences", None))

    if smith := snap(queens_smith):
        src = _src(queens_smith, queens_smith.URL)
        for rec in queens_smith.parse(smith["raw"]):
            typ = COMSOC_TYPES.get(rec["kind"], ItemType.club)
            if typ is ItemType.conference and re.search(r"competition|challenge", rec["name"], re.I):
                typ = ItemType.competition
            items.append(_item(rec, src, _id("comsoc", rec["name"]), typ, "business", "commerce", None))

    if rec_snap := snap(queens_rec):
        src = _src(queens_rec, queens_rec.URL)
        for rec in queens_rec.parse(rec_snap["raw"]):
            is_team = re.search(r"\bteam\b", f"{rec['name']} {rec['description'][:120]}", re.I)
            items.append(_item(rec, src, _id("rec", rec["name"]), ItemType.team if is_team else ItemType.club,
                               "general", None, None, extra_tags={"recreation", "sports"}))

    if ams := snap(queens_ams):
        src = _src(queens_ams, queens_ams.DIRECTORY_URL)
        for rec in queens_ams.parse(ams["raw"]):
            items.append(_item(rec, src, f"ams-{rec['key']}", ItemType.club, "general", None, None))

    items = _merge_duplicates(items)
    _apply_overrides(items, overrides)
    ids = [i.id for i in items]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise ValueError(f"duplicate item ids: {sorted(dupes)}")
    return sorted(items, key=lambda i: (i.name.lower(), i.id))


_STOPWORDS = re.compile(r"\b(?:queen'?s|university|the|of|at|club|association|society|kingston|chapter)\b")


def dedupe_key(name: str) -> str:
    n = re.sub(r"\([^)]*\)", " ", name.lower().replace("’", "'"))
    n = re.sub(r"(?<=\w)'s\b", "", n)  # "Buddha's Light" == "Buddha Light"
    n = _STOPWORDS.sub(" ", n)
    return re.sub(r"[^a-z0-9]+", "", n)


def _merge_duplicates(items: list[Item]) -> list[Item]:
    """The same club listed in two directories becomes one item: the first (most specific)
    listing wins; the other is recorded in ``also_listed_in`` and fills in missing links/tags."""
    kept: dict[str, Item] = {}
    order: list[str] = []
    type_tags = {t.value for t in ItemType}
    for it in items:
        k = dedupe_key(it.name) or it.id
        if k not in kept:
            kept[k] = it
            order.append(k)
            continue
        base = kept[k].model_copy(deep=True)
        base.also_listed_in.append(Listing(source=it.source, name=it.name, listing_url=it.listing_url))
        base.tags = sorted(set(base.tags) | (set(it.tags) - type_tags))
        if not base.links.website and it.links.website:
            base.links.website = it.links.website
        if not base.links.instagram and it.links.instagram:
            base.links.instagram = it.links.instagram
        if not base.apply_url and it.apply_url:
            base.apply_url = it.apply_url
        if not base.description and it.description:
            base.description = it.description
        kept[k] = base
    return [kept[k] for k in order]


def _item(rec: dict[str, Any], src: SourceRef, item_id: str, typ: ItemType, faculty: str,
          subfaculty: str | None, postings: list[dict] | None, *, posting_source: str = "EngSoc Breezy portal",
          extra_tags: set[str] | None = None) -> Item:
    text = rec["description"]
    prov: dict[str, Provenance] = {
        "type": Provenance(method=Method.derived, evidence=f"listed under {rec['kind']}"),
        "faculty": Provenance(method=Method.derived, evidence=f"source: {src.name}"),
    }
    if subfaculty:
        prov["subfaculty"] = Provenance(method=Method.derived, evidence=f"discipline club: {rec['name']}")

    # applications_open
    open_, apply_url = None, rec["website"]
    if postings is not None:
        open_ = bool(postings)
        if postings:
            apply_url = postings[0]["url"]
            prov["applications_open"] = Provenance(
                method=Method.source, evidence="; ".join(p["name"] for p in postings[:5]) + f" ({posting_source})")
        else:
            prov["applications_open"] = Provenance(
                method=Method.source, evidence=f"no active posting ({posting_source})")
    else:
        open_, ev = infer.applications_open(text)
        if ev:
            prov["applications_open"] = Provenance(method=Method.inferred, evidence=ev)

    # eligibility
    fy, ev = infer.first_year_status(f"{rec['name']}. {text}")
    if ev:
        prov["eligibility.first_year"] = Provenance(method=Method.inferred, evidence=ev)
    years, ev = infer.explicit_years(text)
    if ev:
        prov["eligibility.years"] = Provenance(method=Method.inferred, evidence=ev)
    grad, ev = infer.mentions_graduate_students(rec["name"])  # name only: descriptions are too noisy
    if ev:
        prov["eligibility.graduate_students"] = Provenance(method=Method.inferred, evidence=ev)
    if years and fy is None:
        fy = "friendly" if 1 in years else "no"
        prov["eligibility.first_year"] = prov["eligibility.years"]

    hrs, ev = infer.hours_per_week(text)
    if ev:
        prov["time_commitment"] = Provenance(method=Method.inferred, evidence=ev)
    per_week, ev = infer.meetings_per_week(text)
    if ev:
        prov["meetings"] = Provenance(method=Method.inferred, evidence=ev)

    tags = {slugify(c) for c in rec["categories"]}
    tags.add(typ.value)
    tags |= extra_tags or set()
    if subfaculty:
        tags.add(subfaculty)
    kw = infer.keyword_tags(f"{rec['name']}. {text}")
    tags.update(kw)
    prov["tags"] = Provenance(method=Method.inferred if kw else Method.source,
                              evidence=("source categories + keyword rules" if kw else "source categories"))

    return Item(
        id=item_id,
        api_version=API_VERSION,
        school=SCHOOL,
        name=rec["name"],
        type=typ,
        faculty=faculty,
        subfaculty=subfaculty,
        applications_open=open_,
        eligibility=Eligibility(first_year=fy, years=years, graduate_students=grad),
        time_commitment=TimeCommitment(hours_per_week_min=hrs[0], hours_per_week_max=hrs[1]) if hrs else TimeCommitment(),
        meetings=Meetings(per_week=per_week),
        tags=sorted(tags),
        description=text,
        listing_url=rec["listing_url"],
        apply_url=apply_url,
        links=Links(website=rec["website"], instagram=rec["instagram"]),
        source=src,
        source_updated_at=rec["updated_at"],
        provenance=prov,
    )


_OVERRIDABLE = {
    "name", "type", "faculty", "subfaculty", "applications_open", "application_deadline",
    "eligibility", "time_commitment", "meetings", "tags", "apply_url", "description",
}


def _apply_overrides(items: list[Item], overrides: dict[str, dict]) -> None:
    by_id = {i.id: i for i in items}
    unknown = set(overrides) - set(by_id)
    if unknown:
        raise ValueError(f"overrides.yaml references unknown ids: {sorted(unknown)}")
    for item_id, ov in overrides.items():
        ov = dict(ov)
        note = ov.pop("note", None) or "manual override"
        bad = set(ov) - _OVERRIDABLE - {"add_tags"}
        if bad:
            raise ValueError(f"{item_id}: cannot override {sorted(bad)}")
        item = by_id[item_id]
        data = item.model_dump()
        for k, v in ov.items():
            if k == "add_tags":
                data["tags"] = sorted(set(data["tags"]) | set(v))
                k = "tags"
            elif isinstance(v, dict) and isinstance(data.get(k), dict):
                data[k] = {**data[k], **v}
                if k == "meetings" and "per_week" in v:
                    data[k]["frequency"] = None  # recompute label
                if k == "eligibility":  # eligibility provenance is tracked per sub-field
                    # first_year / first_year_friendly mirror each other: an override of one
                    # replaces both, so the model re-derives the other from it.
                    if "first_year" in v and "first_year_friendly" not in v:
                        data[k]["first_year_friendly"] = None
                    elif "first_year_friendly" in v and "first_year" not in v:
                        data[k]["first_year"] = None
                    for sub in v:
                        if sub in ("first_year", "first_year_friendly"):
                            sub = "first_year"
                        data["provenance"][f"{k}.{sub}"] = {"method": Method.override.value, "evidence": note}
                    continue
            else:
                data[k] = v
            data["provenance"][k] = {"method": Method.override.value, "evidence": note}
        new = Item.model_validate(data)
        items[items.index(item)] = new
        by_id[item_id] = new

# Scraper health check used by `ecapi verify`: a source yielding fewer items than this is probably broken.
MIN_ITEMS_PER_SOURCE = {
    queens_ams.SOURCE_ID: 150,
    queens_engsoc.SOURCE_ID: 25,
    queens_compsa.SOURCE_ID: 5,
    queens_hss.SOURCE_ID: 10,
    queens_smith.SOURCE_ID: 30,
    queens_rec.SOURCE_ID: 15,
}
