"""The public contract of the current API version, and the check that stops breaking changes.

``contracts/v{N}.json`` records what clients of version N can rely on: every endpoint path,
the filter segment order and values, each school's faculty/subfaculty URLs, the response
envelope keys, and every item field with its type.

``check()`` compares the code's current contract with that file:

* anything **removed or changed** (a path, a filter value, a faculty URL, a field, a field
  type, an enum value) is a breaking change and fails ``ecapi verify``, so it can't deploy.
  The fix is a new version: freeze the old one and bump ``schema.API_VERSION``.
* anything **added** is fine; ``ecapi contract --write`` records it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import build
from .schema import API_VERSION, Item
from .store import ROOT

CONTRACTS = ROOT / "contracts"
ENVELOPE_KEYS = ["api_version", "deprecated", "school", "data_as_of", "endpoint"]


def _resolve(node: dict, defs: dict) -> dict:
    while "$ref" in node:
        node = defs[node["$ref"].split("/")[-1]]
    return node


def _flatten(node: dict, defs: dict, prefix: str, out: dict[str, dict]) -> None:
    node = _resolve(node, defs)
    variants = node.get("anyOf") or [node]
    types, enums = set(), set()
    obj_variant = None
    for v in variants:
        v = _resolve(v, defs)
        if "enum" in v:
            enums |= {str(x) for x in v["enum"]}
            types.add("string")
        elif "const" in v:
            enums.add(str(v["const"]))
            types.add("string")
        elif v.get("type") == "object" and "properties" in v:
            types.add("object")
            obj_variant = v
        elif v.get("type") == "array":
            items = _resolve(v.get("items", {}), defs)
            inner = "object" if "properties" in items else items.get("type", "any")
            types.add(f"array<{inner}>")
            if "properties" in items:
                obj_variant = items
        else:
            types.add(v.get("type", "any"))
    entry: dict[str, Any] = {"type": "|".join(sorted(types))}
    if enums:
        entry["enum"] = sorted(enums)
    if prefix:
        out[prefix] = entry
    if obj_variant is not None:
        for name, sub in obj_variant["properties"].items():
            _flatten(sub, defs, f"{prefix}.{name}" if prefix else name, out)


def item_fields() -> dict[str, dict]:
    schema = Item.model_json_schema()
    out: dict[str, dict] = {}
    _flatten(schema, schema.get("$defs", {}), "", out)
    return dict(sorted(out.items()))


def current(school_infos: dict[str, dict]) -> dict[str, Any]:
    return {
        "api_version": API_VERSION,
        "paths": sorted(ep["path"] for ep in build.endpoint_guide().values()),
        "filter_dimensions": build.DIMENSIONS,
        "filter_values": {
            "type": build.TYPE_VALUES,
            "app": build.APP_VALUES,
            "first": build.FIRST_VALUES,
        },
        "schools": {
            sid: {
                f"fac-{f}": sorted(["sub-any"] + [f"sub-{s}" for s in finfo.get("subfaculties", {})])
                for f, finfo in sorted(info.get("faculties", {}).items())
            }
            for sid, info in sorted(school_infos.items())
        },
        "envelope_keys": ENVELOPE_KEYS,
        "item_fields": item_fields(),
    }


def path_for(version: str = API_VERSION, contracts: Path = CONTRACTS) -> Path:
    return contracts / f"v{version}.json"


def load(version: str = API_VERSION, contracts: Path = CONTRACTS) -> dict[str, Any] | None:
    p = path_for(version, contracts)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def diff(saved: dict[str, Any], now: dict[str, Any]) -> tuple[list[str], list[str]]:
    """(breaking changes, additions)."""
    breaking, added = [], []

    def sets(name: str, old: list, new: list) -> None:
        for x in sorted(set(old) - set(new)):
            breaking.append(f"{name}: removed {x!r}")
        for x in sorted(set(new) - set(old)):
            added.append(f"{name}: added {x!r}")

    if saved["api_version"] != now["api_version"]:
        breaking.append(f"contract is for v{saved['api_version']} but code is v{now['api_version']}")
    sets("paths", saved["paths"], now["paths"])
    if saved["filter_dimensions"] != now["filter_dimensions"]:
        breaking.append(f"filter segment order changed: {saved['filter_dimensions']} -> {now['filter_dimensions']}")
    for dim, vals in saved["filter_values"].items():
        sets(f"filter values ({dim})", vals, now["filter_values"].get(dim, []))
    for sid, tree in saved["schools"].items():
        new_tree = now["schools"].get(sid)
        if new_tree is None:
            breaking.append(f"school {sid!r} removed")
            continue
        sets(f"{sid} faculties", list(tree), list(new_tree))
        for fac, subs in tree.items():
            if fac in new_tree:
                sets(f"{sid} {fac} subfaculties", subs, new_tree[fac])
    for sid in set(now["schools"]) - set(saved["schools"]):
        added.append(f"school {sid!r} added")
    sets("envelope keys", saved["envelope_keys"], now["envelope_keys"])
    old_f, new_f = saved["item_fields"], now["item_fields"]
    for name, spec in old_f.items():
        if name not in new_f:
            breaking.append(f"item field removed: {name}")
            continue
        if spec["type"] != new_f[name]["type"]:
            breaking.append(f"item field {name}: type {spec['type']} -> {new_f[name]['type']}")
        for e in sorted(set(spec.get("enum", [])) - set(new_f[name].get("enum", []))):
            breaking.append(f"item field {name}: enum value {e!r} removed")
        for e in sorted(set(new_f[name].get("enum", [])) - set(spec.get("enum", []))):
            added.append(f"item field {name}: enum value {e!r} added")
    for name in sorted(set(new_f) - set(old_f)):
        added.append(f"item field added: {name}")
    return breaking, added


BUMP_HELP = ("This is a breaking change for API clients, so it needs a new API version: "
             "see 'Making a breaking change' in systems-usage.md "
             "(build, `ecapi freeze`, bump schema.API_VERSION, `ecapi contract --write`).")


def check(school_infos: dict[str, dict], contracts: Path = CONTRACTS) -> tuple[list[str], list[str]]:
    saved = load(API_VERSION, contracts)
    if saved is None:
        return [f"no contract for v{API_VERSION}: run `ecapi contract --write`"], []
    return diff(saved, current(school_infos))


def write(school_infos: dict[str, dict], contracts: Path = CONTRACTS) -> Path:
    saved = load(API_VERSION, contracts)
    if saved is not None:
        breaking, _ = diff(saved, current(school_infos))
        if breaking:
            raise SystemExit("refusing to rewrite the contract over breaking changes:\n  "
                             + "\n  ".join(breaking) + "\n" + BUMP_HELP)
    p = path_for(API_VERSION, contracts)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(current(school_infos), indent=1) + "\n", encoding="utf-8")
    return p
