"""API versions: which exist, which is current, and freezing a version when it's replaced.

Rule: the current version is built fresh from live data on every deploy. When the URL
layout or response shape has to change in a breaking way, the current version is first
*frozen*: its last build is copied to ``archive/v{N}/`` and every JSON file in it gets
``"deprecated": true`` and a ``deprecation`` block. The new version then becomes current.
Every later deploy keeps serving the frozen copy, so old clients keep working but are told
to move.

State lives in ``api-versions.json`` at the repo root:

    {"v1": {"status": "deprecated", "released": "...", "deprecated_since": "...",
            "successor": "v2", "sunset": null, "data_frozen_at": "..."},
     "v2": {"status": "current", "released": "..."}}
"""

from __future__ import annotations

import datetime as dt
import json
import shutil
from pathlib import Path
from typing import Any

from .schema import API_VERSION
from .store import ROOT

REGISTRY = ROOT / "api-versions.json"
ARCHIVE = ROOT / "archive"
CURRENT = f"v{API_VERSION}"


def load_registry(path: Path = REGISTRY) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {CURRENT: {"status": "current", "released": None}}
    return json.loads(path.read_text(encoding="utf-8"))


def save_registry(reg: dict[str, dict[str, Any]], path: Path = REGISTRY) -> None:
    ordered = dict(sorted(reg.items(), key=lambda kv: int(kv[0][1:])))
    path.write_text(json.dumps(ordered, indent=1) + "\n", encoding="utf-8")


def check_registry(reg: dict[str, dict[str, Any]], archive: Path = ARCHIVE) -> list[str]:
    errors = []
    current = [v for v, e in reg.items() if e.get("status") == "current"]
    if current != [CURRENT]:
        errors.append(f"api-versions.json must mark exactly {CURRENT} (schema.API_VERSION) as current, found {current}")
    for v, e in reg.items():
        if e.get("status") == "deprecated":
            if not (archive / v).is_dir():
                errors.append(f"{v} is deprecated but archive/{v}/ is missing")
            for k in ("deprecated_since", "successor"):
                if not e.get(k):
                    errors.append(f"{v}: deprecated entry needs '{k}'")
        elif e.get("status") != "current":
            errors.append(f"{v}: unknown status {e.get('status')!r}")
    if int(CURRENT[1:]) < max((int(v[1:]) for v in reg), default=0):
        errors.append(f"current version {CURRENT} is older than a registered version")
    return errors


def deprecation_block(version: str, entry: dict[str, Any]) -> dict[str, Any]:
    succ = entry["successor"]
    return {
        "since": entry["deprecated_since"],
        "successor": succ,
        "successor_index": f"{succ}/index.json",
        "sunset": entry.get("sunset"),  # date this version may be removed, or null = no date set
        "data_frozen_at": entry.get("data_frozen_at"),
        "message": entry.get("message") or (
            f"API {version} is deprecated and its data is frozen as of {entry.get('data_frozen_at')}. "
            f"It is no longer updated. Move to {succ}: see {succ}/index.json."),
    }


def _stamp(obj: Any, block: dict[str, Any]) -> Any:
    """Put deprecated/deprecation right after api_version, keeping the rest in order."""
    if not isinstance(obj, dict):
        return obj
    out: dict[str, Any] = {}
    if "api_version" in obj:
        out["api_version"] = obj["api_version"]
    out["deprecated"] = True
    out["deprecation"] = block
    for k, v in obj.items():
        if k not in ("api_version", "deprecated", "deprecation"):
            out[k] = v
    return out


def freeze(site: Path, version: str, successor: str, *, sunset: str | None = None, message: str | None = None,
           archive: Path = ARCHIVE, registry: Path = REGISTRY, today: str | None = None) -> int:
    """Archive ``site/<version>/`` as deprecated. Returns the number of files stamped."""
    src = site / version
    if not src.is_dir():
        raise FileNotFoundError(f"{src} not found: run `ecapi build` before bumping API_VERSION")
    if int(successor[1:]) <= int(version[1:]):
        raise ValueError(f"successor {successor} must be newer than {version}")
    reg = load_registry(registry)
    entry = reg.get(version, {"released": None})
    if entry.get("status") == "deprecated":
        raise ValueError(f"{version} is already frozen")
    frozen_at = json.loads((src / "schools.json").read_text(encoding="utf-8")).get("data_as_of")
    entry.update({
        "status": "deprecated",
        "deprecated_since": today or dt.date.today().isoformat(),
        "successor": successor,
        "sunset": sunset,
        "data_frozen_at": frozen_at,
        "message": message,
    })
    block = deprecation_block(version, entry)
    dest = archive / version
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)
    n = 0
    for p in dest.rglob("*.json"):
        obj = json.loads(p.read_text(encoding="utf-8"))
        p.write_text(json.dumps(_stamp(obj, block), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        n += 1
    reg[version] = entry
    reg.setdefault(successor, {"status": "current", "released": today or dt.date.today().isoformat()})
    save_registry(reg, registry)
    return n


def publish(out: Path, *, archive: Path = ARCHIVE, registry: Path = REGISTRY) -> dict[str, Any]:
    """Copy frozen versions into the site and write the root ``versions.json``."""
    reg = load_registry(registry)
    for v, e in reg.items():
        if e.get("status") == "deprecated":
            shutil.copytree(archive / v, out / v, dirs_exist_ok=False)
    listing = {
        "current": CURRENT,
        "versions": {
            v: {
                "status": e["status"],
                "deprecated": e["status"] == "deprecated",
                "index": f"{v}/index.json",
                **({"deprecation": deprecation_block(v, e)} if e["status"] == "deprecated" else {}),
                **({"released": e.get("released")} if e.get("released") else {}),
            }
            for v, e in sorted(reg.items(), key=lambda kv: int(kv[0][1:]))
        },
    }
    (out / "versions.json").write_text(json.dumps(listing, indent=1) + "\n", encoding="utf-8")
    return listing
