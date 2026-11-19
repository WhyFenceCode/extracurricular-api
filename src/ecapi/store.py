"""Source snapshots on disk (data/<school>/raw/<source>.json) and overrides."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"


def raw_path(school: str, source_id: str, data_dir: Path = DATA) -> Path:
    return data_dir / school / "raw" / f"{source_id}.json"


def load_snapshot(school: str, source_id: str, data_dir: Path = DATA) -> dict[str, Any] | None:
    p = raw_path(school, source_id, data_dir)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def save_snapshot(school: str, source_id: str, raw: dict[str, Any], data_dir: Path = DATA) -> Path:
    p = raw_path(school, source_id, data_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    snap = {
        "source": source_id,
        "fetched_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "via": raw.get("via", "live"),
        "origin_url": raw.get("origin_url"),
        "raw": raw,
    }
    p.write_text(json.dumps(snap, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return p


DEFAULT_MAX_AGE_DAYS = 3.0  # scrape reuses a snapshot younger than this unless forced


def snapshot_age_days(snap: dict[str, Any] | None, now: dt.datetime | None = None) -> float | None:
    """Days since the snapshot was fetched, or None if there is no usable snapshot."""
    if not snap or not snap.get("fetched_at"):
        return None
    fetched = dt.datetime.fromisoformat(snap["fetched_at"])
    now = now or dt.datetime.now(dt.timezone.utc)
    return (now - fetched).total_seconds() / 86400


def is_fresh(snap: dict[str, Any] | None, max_age_days: float, now: dt.datetime | None = None) -> bool:
    age = snapshot_age_days(snap, now)
    return age is not None and age < max_age_days


def load_overrides(school: str, data_dir: Path = DATA) -> dict[str, dict]:
    p = data_dir / school / "overrides.yaml"
    if not p.exists():
        return {}
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{p}: top level must be a mapping of item id -> fields")
    return data
