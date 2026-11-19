import datetime as dt
import types

import pytest

from ecapi import cli, store

NOW = dt.datetime(2026, 11, 19, 12, 0, tzinfo=dt.timezone.utc)


def _snap(days_old: float) -> dict:
    return {"fetched_at": (NOW - dt.timedelta(days=days_old)).isoformat(), "raw": {"records": [1, 2, 3]}}


@pytest.mark.parametrize("days,fresh", [(0.1, True), (2.9, True), (3.0, False), (7, False)])
def test_is_fresh(days, fresh):
    assert store.is_fresh(_snap(days), 3, NOW) is fresh


def test_missing_snapshot_is_never_fresh():
    assert store.is_fresh(None, 3, NOW) is False
    assert store.snapshot_age_days({"raw": {}}, NOW) is None


@pytest.fixture
def fake_school(monkeypatch):
    calls = []
    src = types.SimpleNamespace(
        SOURCE_ID="fake-src",
        fetch=lambda client: calls.append("fetch") or {"records": [1, 2, 3, 4], "via": "live"},
        parse=lambda raw: raw["records"],
    )
    monkeypatch.setattr(cli, "SCHOOLS", {"fake": types.SimpleNamespace(SOURCES=[src])})
    saved = []
    monkeypatch.setattr(store, "save_snapshot", lambda school, sid, raw: saved.append(raw) or "x")
    return calls, saved, monkeypatch


def _run(*argv):
    return cli.main(["scrape", *argv])


def test_fresh_snapshot_is_reused(fake_school):
    calls, saved, mp = fake_school
    one_day_ago = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1)).isoformat()
    mp.setattr(store, "load_snapshot", lambda school, sid: {"fetched_at": one_day_ago, "raw": {"records": [1]}})
    assert _run() == 0
    assert calls == [] and saved == []  # no request made, nothing rewritten


def test_old_snapshot_is_rescraped(fake_school):
    calls, saved, mp = fake_school
    mp.setattr(store, "load_snapshot", lambda school, sid: _snap(10))
    assert _run() == 0
    assert calls == ["fetch"] and len(saved) == 1


def test_force_rescrapes_fresh_snapshot(fake_school):
    calls, saved, mp = fake_school
    mp.setattr(store, "load_snapshot", lambda school, sid: {
        "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(), "raw": {"records": [1]}})
    assert _run("--force") == 0
    assert calls == ["fetch"] and len(saved) == 1


def test_max_age_flag(fake_school):
    calls, saved, mp = fake_school
    two_days_ago = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=2)).isoformat()
    mp.setattr(store, "load_snapshot", lambda school, sid: {"fetched_at": two_days_ago, "raw": {"records": [1]}})
    assert _run("--max-age-days", "1") == 0
    assert calls == ["fetch"]
