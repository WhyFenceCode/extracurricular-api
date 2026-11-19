from ecapi import build, contract, docs
from ecapi.schools import SCHOOLS


def test_docs_folder_is_up_to_date():
    stale = docs.check()
    assert stale == [], f"run `python -m ecapi docs` and commit: {stale}"


def test_every_filter_value_is_documented():
    page = docs.render()["filters.md"]
    for v in build.TYPE_VALUES + build.APP_VALUES + build.FIRST_VALUES:
        assert f"`{v}`" in page, v
    for mod in SCHOOLS.values():
        for f, info in mod.SCHOOL_INFO["faculties"].items():
            assert f"`fac-{f}`" in page
            for s in info.get("subfaculties", {}):
                assert f"`sub-{s}`" in page


def test_every_contract_field_is_documented_with_a_description():
    rows = {r["path"].replace("[]", ""): r for r in docs.field_rows()}
    for path in contract.item_fields():
        assert path in rows, path
        assert rows[path]["description"], f"{path} has no description in schema.py"


def test_every_endpoint_is_documented():
    page = docs.render()["endpoints.md"]
    for ep in build.endpoint_guide().values():
        assert ep["path"] in page
    assert "versions.json" in page


def test_every_school_has_a_page():
    pages = docs.render()
    for sid, mod in SCHOOLS.items():
        page = pages[f"schools/{sid}.md"]
        for s in mod.SOURCES:
            assert s.SOURCE_ID in page
