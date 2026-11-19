import json

import pytest

from ecapi import build, verify
from ecapi.schools import queens


def _build(tmp_path, snapshots, overrides=None):
    items = queens.build_items(snapshots, overrides or {})
    sources = [{"id": s.SOURCE_ID, "name": s.SOURCE_NAME, "fetched_at": "2026-11-19T00:00:00+00:00"} for s in queens.SOURCES]
    build.clean(tmp_path)
    info = build.build_school(tmp_path, queens.SCHOOL_INFO, items, sources, "2026-11-19T00:00:00+00:00")
    build.build_root(tmp_path, [info])
    return items


def _get(tmp_path, rel):
    return json.loads((tmp_path / rel).read_text(encoding="utf-8"))


def _ids(resp):
    return sorted(i["id"] for i in resp["items"])


def test_items_have_expected_values(tmp_path, snapshots):
    items = {i.id: i for i in _build(tmp_path, snapshots)}
    assert set(items) == {
        "ams-youreka-kingston", "ams-debate-union", "ams-grad-chess", "ams-frosh-council",
        "engsoc-qset", "engsoc-queens-baja-sae", "engsoc-qret", "engsoc-wise", "engsoc-it-operations-team",
        "engsoc-civil-dsc", "engsoc-brand-new-dsc",
        "comsoc-qma", "comsoc-qcib", "comsoc-q3c", "comsoc-icbc", "comsoc-design-team",
        "hss-queens-university-anatomy-club", "hss-qha", "hss-hcsrw", "hss-qfsa",
        "compsa-queens-women-in-computing",  # compsa QRET merged into engsoc-qret
        "rec-badminton-club", "rec-run-club", "rec-womens-football-club", "rec-table-tennis-club",
    }

    y = items["ams-youreka-kingston"]
    assert (y.type.value, y.faculty, y.subfaculty) == ("club", "general", None)
    assert y.meetings.per_week == 1.0 and y.meetings.frequency == "weekly"
    assert y.eligibility.first_year == "friendly" and y.eligibility.first_year_friendly is True
    assert y.eligibility.years == [1, 2, 3, 4]
    assert y.applications_open is None  # AMS listings say nothing about applications
    assert y.listing_url == "https://www.myams.org/club/youreka-kingston/"
    assert y.apply_url == "https://linktr.ee/yourekakingston"
    assert {"science-engineering", "club", "research", "biomedical"} <= set(y.tags)
    assert y.provenance["meetings"].method.value == "inferred"

    d = items["ams-debate-union"]
    assert d.name == "Queen's Debate Union"
    assert d.meetings.per_week == 2.0 and d.meetings.frequency == "2x-weekly"
    assert (d.time_commitment.hours_per_week_min, d.time_commitment.hours_per_week_max) == (3, 5)
    assert d.eligibility.first_year == "no" and d.eligibility.first_year_friendly is False
    assert "government-politics" in d.tags  # "&" and "and" variants collapse to one tag

    assert items["ams-grad-chess"].eligibility.graduate_students is True
    fc = items["ams-frosh-council"].eligibility
    assert fc.first_year == "focused" and fc.first_year_friendly is True

    q = items["engsoc-qset"]
    assert (q.type.value, q.faculty) == ("design-team", "engineering")
    assert q.applications_open is True and q.apply_url == "https://x.breezy.hr/p/abc"
    assert "QSET Rover" in q.provenance["applications_open"].evidence
    assert items["engsoc-queens-baja-sae"].applications_open is False  # portal active, no Baja posting
    assert items["engsoc-it-operations-team"].type.value == "committee"
    c = items["engsoc-civil-dsc"]
    assert (c.type.value, c.subfaculty, c.meetings.per_week) == ("discipline-club", "civil-engineering", 0.5)
    assert c.applications_open is None  # discipline clubs don't recruit via Breezy
    assert items["engsoc-brand-new-dsc"].subfaculty is None  # unmapped discipline -> unknown, not guessed


def test_faculty_sources(tmp_path, snapshots):
    items = {i.id: i for i in _build(tmp_path, snapshots)}
    t = lambda i: (items[i].type.value, items[i].faculty, items[i].subfaculty)  # noqa: E731
    assert t("comsoc-qma") == ("club", "business", "commerce")
    assert t("comsoc-qcib") == ("conference", "business", "commerce")
    assert t("comsoc-q3c") == ("competition", "business", "commerce")  # "Challenge" in conference row
    assert t("comsoc-icbc") == ("competition", "business", "commerce")
    assert t("comsoc-design-team") == ("committee", "business", "commerce")  # no doubled "comsoc-comsoc-"
    assert t("hss-qha") == ("club", "health-sciences", "bachelor-health-sciences")
    assert t("compsa-queens-women-in-computing") == ("club", "arts-science", "computing")
    assert t("rec-badminton-club") == ("club", "general", None)
    assert {"recreation", "sports", "sport"} <= set(items["rec-badminton-club"].tags)
    assert items["rec-badminton-club"].meetings.per_week == 1.0
    assert items["rec-womens-football-club"].type.value == "team"

    a = items["hss-queens-university-anatomy-club"]
    assert a.links.instagram == "https://www.instagram.com/qu.anatomy/"
    assert a.eligibility.first_year == "focused"
    assert items["hss-qha"].links.instagram is None  # handle shared by two clubs: unattributable
    assert items["hss-qfsa"].links.instagram is None  # "@clubs.queensu.ca" is an email domain
    assert items["compsa-queens-women-in-computing"].links.instagram == "https://www.instagram.com/queenswic/"

    # Table Tennis reused Football's description on the source page: dropped where it doesn't fit
    assert items["rec-table-tennis-club"].description == ""
    assert "football" in items["rec-womens-football-club"].description.lower()

    q = items["engsoc-qret"]  # listed by EngSoc and COMPSA -> one item
    assert q.source.id == "queens-engsoc"
    assert [x.source.id for x in q.also_listed_in] == ["queens-compsa"]
    assert q.also_listed_in[0].listing_url == "https://compsa.ca/ccr"


def test_declared_faculties_have_endpoints(tmp_path, snapshots):
    _build(tmp_path, snapshots)
    f = "v1/queens/filter"
    for fac in ("education", "law", "graduate"):  # no source yet: valid, empty
        r = _get(tmp_path, f"{f}/fac-{fac}/sub-any/type-any/app-any/first-any.json")
        assert r["count"] == 0
    # a declared subfaculty with no items still resolves
    r = _get(tmp_path, f"{f}/fac-engineering/sub-mining-engineering/type-any/app-any/first-any.json")
    assert r["count"] == 0
    info = _get(tmp_path, "v1/queens/info.json")
    assert info["faculties"]["business"]["items"] == 5
    assert info["faculties"]["law"]["sources"] == []
    assert info["faculties"]["engineering"]["filter"] == f"{f}/fac-engineering/sub-any/type-any/app-any/first-any.json"


def test_endpoint_names(tmp_path, snapshots):
    _build(tmp_path, snapshots)
    for rel in ("v1/index.json", "v1/schools.json", "v1/queens/info.json", "v1/queens/all.json",
                "v1/queens/tags.json", "v1/queens/item/engsoc-qset.json", "v1/queens/tag/robotics.json"):
        assert (tmp_path / rel).exists(), rel
    for old in ("v1/queens/index.json", "v1/queens/meta.json", "v1/queens/items", "v1/queens/tags/"):
        assert not (tmp_path / old).exists(), old
    guide = _get(tmp_path, "v1/index.json")
    for ep in guide["endpoints"].values():
        assert {"path", "returns"} <= set(ep)
        if "example" in ep:
            assert (tmp_path / ep["example"]).exists(), ep["example"]
    assert _get(tmp_path, "v1/queens/all.json")["endpoint"] == "all"


def test_application_status_from_listing_text(tmp_path, snapshots):
    items = {i.id: i for i in _build(tmp_path, snapshots)}
    g = items["ams-grad-chess"]  # "Drop by any week!"
    assert (g.applications_open, g.application_deadline) == (True, "rolling")
    assert g.provenance["applications_open"].method.value == "inferred"
    assert "Drop by any week" in g.provenance["application_deadline"].evidence
    # a posting still wins, and a silent listing stays unknown
    assert items["engsoc-qset"].provenance["applications_open"].method.value == "source"
    assert items["ams-youreka-kingston"].applications_open is None

    f = "v1/queens/filter/fac-any/sub-any/type-any"
    assert _ids(_get(tmp_path, f"{f}/app-rolling/first-any.json")) == ["ams-grad-chess"]
    opened = _ids(_get(tmp_path, f"{f}/app-open/first-any.json"))
    assert "ams-grad-chess" in opened and "engsoc-qset" in opened  # app-open includes rolling


def test_rolling_override_and_contradiction(snapshots):
    items = {i.id: i for i in queens.build_items(snapshots, {
        "ams-youreka-kingston": {"application_deadline": "rolling", "note": "club exec, Nov 2026"}})}
    y = items["ams-youreka-kingston"]
    assert (y.applications_open, y.application_deadline) == (True, "rolling")  # rolling implies open
    with pytest.raises(Exception, match="contradicts"):
        queens.build_items(snapshots, {"ams-youreka-kingston": {
            "application_deadline": "rolling", "applications_open": False}})
    with pytest.raises(Exception, match="pattern"):
        queens.build_items(snapshots, {"ams-youreka-kingston": {"application_deadline": "soon"}})


def test_empty_breezy_means_unknown(tmp_path, snapshots):
    snapshots["queens-engsoc-breezy"]["raw"]["postings"] = []
    items = {i.id: i for i in _build(tmp_path, snapshots)}
    assert items["engsoc-qset"].applications_open is None


def test_filter_endpoints(tmp_path, snapshots):
    _build(tmp_path, snapshots)
    f = "v1/queens/filter"
    assert _ids(_get(tmp_path, f"{f}/fac-engineering/sub-any/type-design-team/app-open/first-any.json")) == ["engsoc-qset"]
    assert _ids(_get(tmp_path, f"{f}/fac-engineering/sub-any/type-design-team/app-closed/first-any.json")) == ["engsoc-qret", "engsoc-queens-baja-sae"]
    assert _ids(_get(tmp_path, f"{f}/fac-engineering/sub-civil-engineering/type-any/app-any/first-any.json")) == ["engsoc-civil-dsc"]
    assert _ids(_get(tmp_path, f"{f}/fac-any/sub-any/type-any/app-any/first-friendly.json")) == [
        "ams-frosh-council", "ams-youreka-kingston", "engsoc-qset",
        "hss-queens-university-anatomy-club", "rec-badminton-club", "rec-run-club"]  # friendly includes focused
    assert _ids(_get(tmp_path, f"{f}/fac-any/sub-any/type-any/app-any/first-focused.json")) == ["ams-frosh-council", "hss-queens-university-anatomy-club"]
    assert _ids(_get(tmp_path, f"{f}/fac-general/sub-any/type-club/app-unknown/first-no.json")) == ["ams-debate-union"]
    empty = _get(tmp_path, f"{f}/fac-general/sub-any/type-design-team/app-any/first-any.json")
    assert empty["count"] == 0 and empty["items"] == []
    assert _get(tmp_path, f"{f}/fac-any/sub-any/type-any/app-any/first-any.json")["count"] == 25
    q = _get(tmp_path, f"{f}/fac-engineering/sub-any/type-design-team/app-open/first-friendly.json")["query"]
    assert q == {"faculty": "fac-engineering", "subfaculty": "sub-any", "type": "type-design-team",
                 "app": "app-open", "first": "first-friendly"}
    # subfaculty values exist only under their own faculty
    assert not (tmp_path / f / "fac-general" / "sub-civil-engineering").exists()
    assert not (tmp_path / f / "fac-any" / "sub-civil-engineering").exists()
    # no bare yes/no segments anywhere
    segs = {p.name for p in (tmp_path / f).rglob("*")}
    assert not segs & {"yes", "no", "any", "yes.json", "no.json", "any.json", "unknown.json"}
    assert _ids(_get(tmp_path, "v1/queens/tag/government-politics.json")) == ["ams-debate-union"]
    one = _get(tmp_path, "v1/queens/item/engsoc-qset.json")
    assert one["api_version"] == "1" and one["school"] == "queens" and one["item"]["name"].endswith("(QSET)")


def test_verify_passes_and_catches_tampering(tmp_path, snapshots):
    _build(tmp_path, snapshots)
    assert verify.verify_school(tmp_path, "queens") == []
    assert verify.verify_root(tmp_path) == []

    p = tmp_path / "v1/queens/filter/fac-engineering/sub-any/type-design-team/app-open/first-any.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    data["items"] = []
    p.write_text(json.dumps(data), encoding="utf-8")
    errs = verify.verify_school(tmp_path, "queens")
    assert any("type-design-team/app-open/first-any.json" in e.replace("\\", "/") for e in errs)


def test_verify_flags_broken_scraper(tmp_path, snapshots):
    _build(tmp_path, snapshots)
    errs = verify.verify_school(tmp_path, "queens", {"queens-ams": 150})
    assert any("queens-ams" in e for e in errs)


def test_overrides(tmp_path, snapshots):
    items = {i.id: i for i in _build(tmp_path, snapshots, {
        "engsoc-queens-baja-sae": {
            "time_commitment": {"hours_per_week_min": 5, "hours_per_week_max": 10},
            "meetings": {"per_week": 2},
            "eligibility": {"first_year_friendly": True},
            "add_tags": ["off-road"],
            "note": "confirmed with team lead 2026-11",
        }
    })}
    b = items["engsoc-queens-baja-sae"]
    assert b.time_commitment.hours_per_week_max == 10
    assert b.meetings.frequency == "2x-weekly"
    assert b.eligibility.first_year == "friendly" and b.eligibility.first_year_friendly is True
    assert "off-road" in b.tags and "design-team" in b.tags
    assert b.provenance["eligibility.first_year"].method.value == "override"
    assert b.provenance["meetings"].evidence == "confirmed with team lead 2026-11"


def test_override_first_year_replaces_inferred(tmp_path, snapshots):
    # Debate Union is inferred "no"; a human override to focused must win cleanly.
    items = {i.id: i for i in queens.build_items(snapshots, {"ams-debate-union": {"eligibility": {"first_year": "focused"}}})}
    e = items["ams-debate-union"].eligibility
    assert (e.first_year, e.first_year_friendly) == ("focused", True)
    items = {i.id: i for i in queens.build_items(snapshots, {"ams-debate-union": {"eligibility": {"first_year_friendly": True}}})}
    e = items["ams-debate-union"].eligibility
    assert (e.first_year, e.first_year_friendly) == ("friendly", True)


@pytest.mark.parametrize("ov,msg", [
    ({"nope": {"name": "x"}}, "unknown ids"),
    ({"engsoc-qset": {"listing_url": "https://x"}}, "cannot override"),
    ({"engsoc-qset": {"meetings": {"per_week": 99}}}, "less than or equal"),
    ({"engsoc-qset": {"eligibility": {"first_year": "maybe"}}}, "focused"),
])
def test_bad_overrides_rejected(tmp_path, snapshots, ov, msg):
    with pytest.raises(Exception, match=msg):
        queens.build_items(snapshots, ov)
