"""Command line: ``python -m ecapi scrape|build|verify``."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from . import build as builder
from . import contract, docs, store, verify, versions
from .http import PoliteClient
from .schools import SCHOOLS

log = logging.getLogger("ecapi")


def _gh(level: str, msg: str) -> None:
    """Print a GitHub Actions annotation (harmless locally)."""
    print(f"::{level}::{msg}")


def cmd_scrape(args) -> int:
    failures = 0
    with PoliteClient() as client:
        for school_id in args.school or list(SCHOOLS):
            mod = SCHOOLS[school_id]
            for src in mod.SOURCES:
                if args.source and src.SOURCE_ID not in args.source:
                    continue
                old = store.load_snapshot(school_id, src.SOURCE_ID)
                if not args.force and store.is_fresh(old, args.max_age_days):
                    age = store.snapshot_age_days(old)
                    log.info("%s: snapshot is %.1f days old (< %g); reusing it (--force to re-scrape)",
                             src.SOURCE_ID, age, args.max_age_days)
                    continue
                try:
                    raw = src.fetch(client)
                    n_new = len(src.parse(raw))
                except Exception as e:  # noqa: BLE001 - keep last good snapshot on any failure
                    failures += 1
                    _gh("warning", f"{src.SOURCE_ID}: fetch failed ({e}); keeping previous snapshot")
                    continue
                n_old = len(src.parse(old["raw"])) if old else 0
                if n_old and n_new < n_old * 0.5:
                    failures += 1
                    _gh("warning", f"{src.SOURCE_ID}: {n_new} records vs {n_old} last time; keeping previous snapshot")
                    continue
                p = store.save_snapshot(school_id, src.SOURCE_ID, raw)
                log.info("%s: %d records (%s) -> %s", src.SOURCE_ID, n_new, raw.get("via"), p)
    return 1 if (failures and args.strict) else 0


def cmd_build(args) -> int:
    out = Path(args.out)
    builder.clean(out)
    schools = []
    for school_id, mod in SCHOOLS.items():
        snaps = {s.SOURCE_ID: store.load_snapshot(school_id, s.SOURCE_ID) for s in mod.SOURCES}
        items = mod.build_items(snaps, store.load_overrides(school_id))
        sources_meta = []
        for s in mod.SOURCES:
            snap = snaps[s.SOURCE_ID]
            sources_meta.append({
                "id": s.SOURCE_ID, "name": s.SOURCE_NAME,
                "fetched_at": snap["fetched_at"] if snap else None,
                "via": snap["via"] if snap else None,
                "url": snap["origin_url"] if snap else None,
                "items": sum(1 for i in items if i.source.id == s.SOURCE_ID),
            })
            pages = (snap or {}).get("raw", {}).get("pages", {})
            archived = sorted(p["archived_at"] for p in pages.values() if p.get("archived_at"))
            if archived:  # served from the Internet Archive because the live site was down
                sources_meta[-1]["archived_at"] = archived[0]
        as_of = max((m["fetched_at"] for m in sources_meta if m["fetched_at"]), default=None)
        schools.append(builder.build_school(out, mod.SCHOOL_INFO, items, sources_meta, as_of))
        log.info("%s: %d items", school_id, len(items))
    builder.build_root(out, schools)
    listing = versions.publish(out)  # copies frozen (deprecated) versions alongside the current one
    log.info("versions: current %s, all %s", listing["current"], list(listing["versions"]))
    return 0


def _school_infos() -> dict[str, dict]:
    return {sid: mod.SCHOOL_INFO for sid, mod in SCHOOLS.items()}


def cmd_verify(args) -> int:
    site = Path(args.out)
    errors = verify.verify_root(site)
    # versioning rules: registry consistent, frozen versions stamped, no unversioned breaking change
    errors += versions.check_registry(versions.load_registry())
    errors += verify.verify_versions(site, versions.load_registry())
    breaking, added = contract.check(_school_infos())
    if breaking:
        errors += [f"breaking change in {versions.CURRENT}: {b}" for b in breaking]
        _gh("error", contract.BUMP_HELP)
    for a in added:
        _gh("notice", f"contract addition (run `ecapi contract --write` to record it): {a}")
    for school_id, mod in SCHOOLS.items():
        errs = verify.verify_school(site, school_id, getattr(mod, "MIN_ITEMS_PER_SOURCE", None))
        errors += [f"{school_id}: {e}" for e in errs]
    for e in errors[:50]:
        _gh("error", e)
    print(f"verify: {len(errors)} error(s)")
    return 1 if errors else 0


def cmd_contract(args) -> int:
    if args.write:
        print(f"wrote {contract.write(_school_infos())}")
        return 0
    breaking, added = contract.check(_school_infos())
    for b in breaking:
        print(f"BREAKING  {b}")
    for a in added:
        print(f"added     {a}")
    if breaking:
        print(contract.BUMP_HELP)
    elif not added:
        print(f"{versions.CURRENT} matches its contract")
    return 1 if breaking else 0


def cmd_docs(args) -> int:
    if args.check:
        stale = docs.check()
        for rel in stale:
            _gh("error", f"docs/{rel} is out of date: run `python -m ecapi docs` and commit the result")
        print(f"docs: {len(stale)} stale page(s)")
        return 1 if stale else 0
    for p in docs.write():
        print(f"wrote {p}")
    return 0


def cmd_freeze(args) -> int:
    n = versions.freeze(Path(args.out), args.version, args.successor, sunset=args.sunset, message=args.message)
    print(f"froze {args.version}: {n} files stamped deprecated -> archive/{args.version}/ (successor {args.successor})")
    print(f"next: set API_VERSION = \"{args.successor[1:]}\" in src/ecapi/schema.py, make your changes, "
          "then `ecapi contract --write`, build and verify")
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    p = argparse.ArgumentParser(prog="ecapi")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scrape", help="fetch sources into data/<school>/raw/")
    s.add_argument("--school", action="append")
    s.add_argument("--source", action="append", help="only these source ids")
    s.add_argument("--strict", action="store_true", help="exit 1 if any source fails")
    s.add_argument("--force", action="store_true", help="re-scrape even sources with a fresh snapshot")
    s.add_argument("--max-age-days", type=float, default=store.DEFAULT_MAX_AGE_DAYS,
                   help=f"reuse snapshots younger than this (default {store.DEFAULT_MAX_AGE_DAYS:g})")
    s.set_defaults(fn=cmd_scrape)
    b = sub.add_parser("build", help="generate the static API")
    b.add_argument("--out", default="site")
    b.set_defaults(fn=cmd_build)
    v = sub.add_parser("verify", help="check a built site")
    v.add_argument("--out", default="site")
    v.set_defaults(fn=cmd_verify)
    c = sub.add_parser("contract", help="compare the current version with contracts/v{N}.json")
    c.add_argument("--write", action="store_true", help="record additions (refuses breaking changes)")
    c.set_defaults(fn=cmd_contract)
    d = sub.add_parser("docs", help="generate the docs/ section from the code")
    d.add_argument("--check", action="store_true", help="exit 1 if docs/ is out of date (CI)")
    d.set_defaults(fn=cmd_docs)
    f = sub.add_parser("freeze", help="archive a built version as deprecated before a breaking change")
    f.add_argument("version", help="the version being replaced, e.g. v1")
    f.add_argument("--successor", required=True, help="the new version, e.g. v2")
    f.add_argument("--sunset", help="YYYY-MM-DD the old version may be removed (optional)")
    f.add_argument("--message", help="custom deprecation message")
    f.add_argument("--out", default="site", help="built site containing the version to freeze")
    f.set_defaults(fn=cmd_freeze)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
