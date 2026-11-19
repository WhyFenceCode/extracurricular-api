import copy
import json

import pytest

from ecapi import build, contract, verify, versions
from ecapi.schools import SCHOOLS, queens

INFOS = {sid: mod.SCHOOL_INFO for sid, mod in SCHOOLS.items()}


# --- contract: breaking changes must not slip into the current version -------------------

def test_repo_contract_matches_code():
    """Fails if someone changed endpoints/fields without bumping the API version."""
    breaking, _ = contract.check(INFOS)
    assert breaking == [], "\n".join(breaking) + "\n" + contract.BUMP_HELP


def _now():
    return contract.current(INFOS)


@pytest.mark.parametrize("mutate,expect", [
    (lambda c: c["paths"].append("v1/{school}/old.json"), "paths: removed 'v1/{school}/old.json'"),
    (lambda c: c["filter_values"]["app"].append("app-maybe"), "filter values (app): removed 'app-maybe'"),
    (lambda c: c["filter_dimensions"].reverse(), "filter segment order changed"),
    (lambda c: c["schools"]["queens"].update({"fac-dentistry": ["sub-any"]}), "queens faculties: removed 'fac-dentistry'"),
    (lambda c: c["schools"]["queens"]["fac-engineering"].append("sub-naval"), "subfaculties: removed 'sub-naval'"),
    (lambda c: c["envelope_keys"].append("page"), "envelope keys: removed 'page'"),
    (lambda c: c["item_fields"].update({"rating": {"type": "number"}}), "item field removed: rating"),
    (lambda c: c["item_fields"]["applications_open"].update({"type": "string"}), "item field applications_open: type"),
    (lambda c: c["item_fields"]["type"]["enum"].append("society"), "enum value 'society' removed"),
])
def test_removals_and_changes_are_breaking(mutate, expect):
    # The saved contract has something the code no longer has -> breaking.
    saved = copy.deepcopy(_now())
    mutate(saved)
    breaking, _ = contract.diff(saved, _now())
    assert any(expect in b for b in breaking), breaking


def test_additions_are_not_breaking():
    saved = copy.deepcopy(_now())
    saved["filter_values"]["type"].remove("type-competition")
    saved["item_fields"].pop("also_listed_in")
    saved["schools"]["queens"].pop("fac-law")
    breaking, added = contract.diff(saved, _now())
    assert breaking == []
    assert any("type-competition" in a for a in added)
    assert any("also_listed_in" in a for a in added)
    assert any("fac-law" in a for a in added)


def test_contract_write_refuses_breaking_change(tmp_path):
    saved = copy.deepcopy(_now())
    saved["paths"].append("v1/{school}/gone.json")
    (tmp_path / "v1.json").write_text(json.dumps(saved), encoding="utf-8")
    with pytest.raises(SystemExit, match="breaking"):
        contract.write(INFOS, tmp_path)


def test_missing_contract_is_an_error(tmp_path):
    breaking, _ = contract.check(INFOS, tmp_path)
    assert breaking and "no contract" in breaking[0]


# --- freezing an old version ----------------------------------------------------------------

@pytest.fixture
def built_site(tmp_path, snapshots):
    site = tmp_path / "site"
    items = queens.build_items(snapshots, {})
    build.clean(site)
    info = build.build_school(site, queens.SCHOOL_INFO, items, [], "2026-11-19T00:00:00+00:00")
    build.build_root(site, [info])
    return site


def test_current_version_responses_say_not_deprecated(built_site):
    for p in [built_site / "v1/queens/all.json", built_site / "v1/queens/item/engsoc-qset.json",
              built_site / "v1/schools.json", built_site / "v1/index.json"]:
        assert json.loads(p.read_text(encoding="utf-8"))["deprecated"] is False


def test_freeze_stamps_every_file_and_updates_registry(tmp_path, built_site):
    reg, archive = tmp_path / "api-versions.json", tmp_path / "archive"
    versions.save_registry({"v1": {"status": "current", "released": "2026-11-19"}}, reg)
    n = versions.freeze(built_site, "v1", "v2", sunset="2027-09-01", archive=archive, registry=reg,
                        today="2027-01-10")
    files = list((archive / "v1").rglob("*.json"))
    assert n == len(files) > 3000

    for p in [archive / "v1/queens/all.json", archive / "v1/queens/item/engsoc-qset.json",
              archive / "v1/queens/filter/fac-engineering/sub-any/type-design-team/app-any/first-any.json",
              archive / "v1/index.json"]:
        obj = json.loads(p.read_text(encoding="utf-8"))
        assert list(obj)[:3] == ["api_version", "deprecated", "deprecation"]
        assert obj["api_version"] == "1" and obj["deprecated"] is True
        d = obj["deprecation"]
        assert d["since"] == "2027-01-10" and d["successor"] == "v2" and d["sunset"] == "2027-09-01"
        assert d["data_frozen_at"] == "2026-11-19T00:00:00+00:00"
        assert d["successor_index"] == "v2/index.json"
        assert "frozen" in d["message"]
    # the data itself is unchanged
    old = json.loads((built_site / "v1/queens/all.json").read_text(encoding="utf-8"))
    new = json.loads((archive / "v1/queens/all.json").read_text(encoding="utf-8"))
    assert new["items"] == old["items"]

    r = versions.load_registry(reg)
    assert r["v1"]["status"] == "deprecated" and r["v1"]["successor"] == "v2"
    assert r["v2"] == {"status": "current", "released": "2027-01-10"}

    with pytest.raises(ValueError, match="already frozen"):
        versions.freeze(built_site, "v1", "v2", archive=archive, registry=reg)


def test_freeze_rejects_bad_successor(tmp_path, built_site):
    with pytest.raises(ValueError, match="newer"):
        versions.freeze(built_site, "v1", "v1", archive=tmp_path / "a", registry=tmp_path / "r.json")


def test_publish_serves_deprecated_version_alongside_current(tmp_path, built_site):
    reg, archive = tmp_path / "api-versions.json", tmp_path / "archive"
    versions.save_registry({"v1": {"status": "current", "released": "2026-11-19"}}, reg)
    versions.freeze(built_site, "v1", "v2", archive=archive, registry=reg, today="2027-01-10")

    out = tmp_path / "next-site"
    (out / "v2").mkdir(parents=True)  # stands in for the newly built current version
    listing = versions.publish(out, archive=archive, registry=reg)
    assert (out / "v1/queens/all.json").exists()
    assert listing["versions"]["v1"]["deprecated"] is True
    assert listing["versions"]["v1"]["deprecation"]["successor"] == "v2"
    assert listing["versions"]["v2"]["status"] == "current"

    r = versions.load_registry(reg)
    errs = verify.verify_versions(out, r)
    assert not [e for e in errs if "not stamped" in e]

    # an unstamped file inside a deprecated version is caught
    p = out / "v1/queens/tags.json"
    obj = json.loads(p.read_text(encoding="utf-8"))
    obj.pop("deprecation")
    p.write_text(json.dumps(obj), encoding="utf-8")
    assert any("1 file(s) not stamped" in e for e in verify.verify_versions(out, r))


def test_registry_rules(tmp_path):
    archive = tmp_path / "archive"
    ok = {"v1": {"status": "current", "released": None}}
    assert versions.check_registry(ok, archive) == []
    # deprecating the version the code still builds, without bumping, is an error
    stale = {"v1": {"status": "deprecated", "deprecated_since": "2027-01-01", "successor": "v2"},
             "v2": {"status": "current"}}
    errs = versions.check_registry(stale, archive)
    assert any("exactly v1" in e for e in errs)
    assert any("archive/v1/ is missing" in e for e in errs)
