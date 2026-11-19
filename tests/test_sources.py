from conftest import AMS_RAW, BREEZY_RAW, ENGSOC_RAW

from ecapi.sources import queens_ams, queens_breezy, queens_engsoc


def test_ams_parse():
    recs = {r["key"]: r for r in queens_ams.parse(AMS_RAW)}
    y = recs["youreka-kingston"]
    assert y["name"] == "Youreka Kingston"
    assert y["website"] == "https://linktr.ee/yourekakingston"  # tracking params stripped, attachment link skipped
    assert y["instagram"] is None
    assert y["categories"] == ["Science & Engineering"]
    assert "Learn More" not in y["description"]
    assert y["description"].startswith("Empowers youth")
    d = recs["debate-union"]
    assert d["name"] == "Queen's Debate Union"
    assert d["instagram"] == "https://www.instagram.com/qdu/"
    assert d["website"] is None
    assert d["categories"] == ["Government & Politics", "Government and Politics"]


def test_engsoc_parse():
    recs = {r["name"]: r for r in queens_engsoc.parse(ENGSOC_RAW)}
    assert set(recs) == {"Queen's Space Engineering Team (QSET)", "Queen's Baja SAE", "Queen's Rocket Engineering Team (QRET)",
                         "Women in Science and Engineering (WiSE)", "IT Operations Team", "Civil DSC", "Brand New DSC"}
    q = recs["Queen's Space Engineering Team (QSET)"]
    assert q["kind"] == "design-team"
    assert q["website"] == "https://team.example/"  # envelope "http://x@..." pseudo-link ignored
    assert q["instagram"] == "https://www.instagram.com/Quee/"
    assert q["listing_url"] == "https://www.engsoc.queensu.ca/get-involved/design-teams/"
    assert recs["IT Operations Team"]["website"] is None


def test_breezy_parse():
    (p,) = queens_breezy.parse(BREEZY_RAW)
    assert p == {"name": "QSET Rover Electrical Member", "department": "Design Teams",
                 "url": "https://x.breezy.hr/p/abc", "published": "2026-09-01"}
