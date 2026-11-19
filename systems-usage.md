# Systems usage (maintainer guide)

How this repo works, how to run it, and how to keep it healthy. The public-facing docs are in
`README.md`; this file is for whoever maintains the system.

## The big picture

```
 sources (school websites)            data/queens/raw/*.json             site/  (GitHub Pages)
 ─────────────────────────   scrape   ───────────────────────   build   ─────────────────────
 AMS WordPress API          ───────▶  one snapshot per source  ───────▶  v1/... JSON files
 EngSoc pages (+ Wayback)              committed to git                  (~3,400 files)
 EngSoc Breezy postings                                                       │
 COMPSA API, HSS, ComSoc,              data/queens/overrides.yaml ──────▶     │ verify
 Athletics rec page                    (your manual corrections)              ▼
                                                                         deploy if 0 errors
```

There are three stages, and each one can run without the others:

1. **scrape** (`python -m ecapi scrape`): fetches every source and saves the raw response to
   `data/<school>/raw/<source>.json`. This is the only stage that touches the network.
2. **build** (`python -m ecapi build --out site`): reads the snapshots plus `overrides.yaml`
   and writes every endpoint into `site/`. No network.
3. **verify** (`python -m ecapi verify --out site`): re-reads `site/` and checks it with a
   separate implementation, and enforces the versioning rules (see below). Exit code 1 means something is wrong, and CI won't deploy.

Raw snapshots are committed on purpose. You can rebuild at any time, after a parser fix or a new
override, without re-scraping, and git history becomes a record of how each directory changed.

## Running it locally

```bash
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"      # macOS/Linux: .venv/bin/pip
.venv/Scripts/python -m pytest -q
.venv/Scripts/python -m ecapi build --out site
.venv/Scripts/python -m ecapi verify --out site
.venv/Scripts/python -m http.server -d site 8000   # then open http://localhost:8000
```

Scraping:

```bash
.venv/Scripts/python -m ecapi scrape                           # sources older than 3 days (see below)
.venv/Scripts/python -m ecapi scrape --force                   # every source, even fresh ones (~45 min)
.venv/Scripts/python -m ecapi scrape --max-age-days 1          # change the reuse threshold
.venv/Scripts/python -m ecapi scrape --source queens-hss       # just one source
.venv/Scripts/python -m ecapi scrape --strict                  # exit 1 if any source fails
```

**Fresh snapshots are reused.** A source whose snapshot was fetched less than 3 days ago
(`DEFAULT_MAX_AGE_DAYS` in `src/ecapi/store.py`) is skipped: no request is made and the file isn't
touched. That means:

- the Monday scheduled run always re-scrapes everything, since its data is a week old;
- a manual "Run workflow" within 3 days of the last scrape reuses the data and finishes in a minute
  or two instead of waiting ~40 min on AMS. Tick **force** in the run dialog to re-scrape anyway;
- after a source *fails*, its snapshot keeps its old `fetched_at`, so the next run retries it.

**Why it's slow:** the AMS site's robots.txt asks for `Crawl-delay: 600` (10 minutes between
requests). The scraper obeys it, and the AMS needs 5 requests, so that's about 40 minutes. Other
sites use a 3-second default or whatever their robots.txt says. For local debugging only, you
can cap the delay with `ECAPI_MAX_CRAWL_DELAY=5`. **Never set this in CI**: it would ignore a
site's explicit request.

## Sources

| Source id | What | How it's fetched | Health floor |
|---|---|---|---|
| `queens-ams` | AMS clubs (faculty `general`) | WordPress REST `/wp-json/wp/v2/club` + `club-categories` | 150 |
| `queens-engsoc` | Design teams, EngSoc clubs, discipline clubs | 3 directory pages; Internet Archive copy if the live site is down | 25 |
| `queens-engsoc-breezy` | EngSoc recruitment postings | Breezy HR public `/json` | n/a |
| `queens-compsa` | Computing clubs + openings | `compsa.ca/api/ccr/clubs`, `/api/ccr/openings` | 5 |
| `queens-hss` | Health Sciences clubs | Squarespace page, parsed as description → name → contact blocks | 10 |
| `queens-comsoc` | Commerce clubs/conferences/competitions | Table on the Smith BCom page (names only) | 30 |
| `queens-rec` | Athletics & Recreation clubs | Sidearm page, one paragraph per club | 15 |

The **health floor** (`MIN_ITEMS_PER_SOURCE` in `src/ecapi/schools/queens.py`) is the minimum item
count `verify` accepts from a source. Falling below it nearly always means the site's HTML changed
and the parser broke.

### What happens when a source fails

- **Fetch error** (site down, DNS failure, 5xx): the old snapshot is kept, and a `::warning::`
  appears in the Actions log.
- **Result much smaller than last time** (under 50%): the old snapshot is kept, with a warning.
- **EngSoc live site down:** it falls back to the most recent Internet Archive copy, and
  `info.json → sources` shows `via: wayback` with `archived_at`. When this was written, the EngSoc
  domain's DNS was broken, so the data came from a July 2026 archive copy. This was added as EngSoc seems to go down offten (go figure), and so it felt like makeing fun of them was the least we could do.
- **Recruitment boards empty** (Breezy, COMPSA openings): `applications_open` stays `null`. An empty
  board can't tell "nobody's hiring" from "the board moved", so the code never infers `false` from it.

## Fixing data by hand: `data/queens/overrides.yaml`

Most directories never state hours, meeting cadence or application windows. When you learn one
(a recruitment post, the club's site, an email), add it here:

```yaml
engsoc-qset:
  applications_open: true
  application_deadline: "2026-09-20"          # or "rolling" for always open
  time_commitment: {hours_per_week_min: 4, hours_per_week_max: 8}
  meetings: {per_week: 1}                     # 0.5 biweekly, 2 twice a week, 0.25 monthly
  eligibility: {first_year: friendly}         # focused | friendly | no
  add_tags: [rover]
  note: "QSET recruitment post, Sept 2026"    # shows up as provenance evidence
```

- Keys are item ids; look them up in `site/v1/queens/all.json` or `item/{id}.json`.
- Overridable fields: `name, type, faculty, subfaculty, applications_open, application_deadline,
  eligibility, time_commitment, meetings, tags, add_tags, apply_url, description`.
- Always write a `note`. It's what API users see as the evidence.
- The build fails, so the change never ships, on an unknown id, a field that can't be overridden,
  or an out-of-range value (e.g. `per_week: 99`).
- Push the change. The push-triggered workflow rebuilds and deploys from the existing snapshots,
  with no re-scrape.

**Remember to expire time-sensitive overrides.** `applications_open: true` stays true until you
remove it. Review the file at the start and end of each recruitment season.

### Removal requests

The site's privacy page (`src/ecapi/static/privacy.html`) tells clubs they can ask for a correction
or removal by opening a GitHub issue, and that removals stick. To honour one:

```yaml
ams-some-club:
  exclude: true
  note: "removal requested by club exec, issue #12"
```

The item disappears from every endpoint on the next build (push to deploy) and stays out after
future scrapes. Keep the entry: deleting it would bring the item back. An excluded id that later
vanishes from its source doesn't cause an error.

If you change what the site or scraper collects (adding analytics, a form, or a source that includes
personal details), **update `privacy.html`** and its "Last updated" date. A test fails if either page
starts loading anything from another site.

## How values get decided

- `inferred` values come from rules in `src/ecapi/infer.py` (hours, meeting cadence, first-year
  status, open applications, keyword tags). They only fire on explicit phrases, and each one stores
  the matched text as `evidence`.
- If you see a bad inference in the live data, add the exact sentence as a test case in
  `tests/test_infer.py`, then tighten the regex until the test passes. That's how the "welcoming
  space" → aerospace and "an environment where" → sustainability false positives were fixed.
- **First-year status** is checked in this order: `no` (e.g. "upper-year only"), then `focused`
  (e.g. "First Year Council", "for first-year students", "transition to university"), then
  `friendly` (e.g. "all years", "no experience required").
- **Duplicates:** items are built in source-priority order (EngSoc, COMPSA, HSS, ComSoc, Rec,
  AMS). Two items whose names normalise to the same key (with "Queen's", "club", "association",
  parentheses and punctuation removed) are merged. The first one wins, and the other is recorded
  in `also_listed_in`.

## The endpoint layout

```
versions.json                      every API version + which is current (never moves)
v1/index.json                      endpoint guide (machine-readable version of the README table)
v1/schools.json
v1/{school}/info.json              faculties + subfaculties, sources, filter values with counts
v1/{school}/all.json
v1/{school}/item/{id}.json
v1/{school}/tags.json
v1/{school}/tag/{tag}.json
v1/{school}/filter/fac-*/sub-*/type-*/app-*/first-*.json
```

Every filter combination is pre-generated, because GitHub Pages can only serve files. The count is
(faculty/subfaculty pairs) × 8 types × 5 app values × 5 first values. For Queen's that's 21 × 200 =
4,200 files, about 15–30 MB depending on item count (Pages allows 1 GB). Every faculty and subfaculty declared in `SCHOOL_INFO` gets endpoints
even with zero items, so URLs stay stable as sources come and go.

## Public docs (`docs/`)

`docs/` is the human-readable reference for API users: endpoints, filters, responses, fields,
versions, and one page per school. **It's generated, so don't edit it by hand:**

```bash
python -m ecapi docs           # regenerate after changing schema descriptions, filters, faculties, sources
python -m ecapi docs --check   # what CI runs; fails if docs/ doesn't match the code
```

Where the words come from:

| Docs page | Edit this instead |
|---|---|
| fields.md | `Field(description=...)` in `src/ecapi/schema.py` (also `METHOD_DOCS`) |
| filters.md | `VALUE_DOCS` in `src/ecapi/build.py`; faculty names in each school's `SCHOOL_INFO` |
| endpoints.md | `endpoint_guide()` in `src/ecapi/build.py` |
| responses.md | `ENVELOPE_DOCS` / `ENDPOINT_EXTRA` in `src/ecapi/docs.py` |
| versions.md | `api-versions.json` (via `ecapi freeze`) |
| schools/<id>.md | `SCHOOL_INFO` and the source modules' docstrings |

A test also fails if any item field, filter value, faculty, endpoint or source is missing from the docs.

## Versioning: the rule, and how it's enforced

**Within a version, things are only added.** Removing or renaming a path, a filter value, a
faculty/subfaculty URL, an envelope key or an item field, or changing a field's type or removing
an enum value, needs a new version. The old version then stays online, frozen and marked deprecated.

The pieces:

| File | Role |
|---|---|
| `src/ecapi/schema.py` → `API_VERSION` | The version the code builds. Every path prefix and `api_version` field comes from it |
| `contracts/v{N}.json` | What clients of vN rely on: paths, filter order and values, faculty URLs, envelope keys, every item field and its type. Generated by `ecapi contract --write` |
| `api-versions.json` | Registry: which versions exist, which is current, and when each was deprecated, its successor, sunset date and frozen-data date |
| `archive/v{N}/` | Frozen copy of each deprecated version, every JSON stamped `"deprecated": true` + `deprecation` |
| `site/versions.json` | Public list of versions (generated from the registry) |

How it's enforced: `ecapi verify` runs in CI before every deploy, and fails (so nothing ships) when:

- the code's contract differs from `contracts/v{N}.json` in a **breaking** way;
- `api-versions.json` doesn't mark exactly the code's version as current;
- a deprecated version has no archive, or any file in it lacks the deprecation stamp;
- any current-version response is missing `"deprecated": false`.

`tests/test_versioning.py::test_repo_contract_matches_code` fails locally too, so you'll find out
before pushing.

Additive changes (a new faculty, filter value, type or field) pass, and CI shows a `::notice::`.
Run `ecapi contract --write` to record them; it **refuses** if anything breaking is pending.

### Making a breaking change (v1 → v2)

```bash
# 1. Build the current version from the code as it is now, BEFORE changing anything
python -m ecapi build --out site

# 2. Freeze it: copies site/v1 -> archive/v1, stamps every file deprecated, updates api-versions.json
python -m ecapi freeze v1 --successor v2 --sunset 2027-09-01     # --sunset is optional

# 3. Bump the version in src/ecapi/schema.py
#      API_VERSION = "2"     and   api_version: Literal["2"]

# 4. Make your breaking change, then record the new contract
python -m ecapi contract --write          # writes contracts/v2.json

# 5. Build + verify: serves v2 (live) and v1 (frozen, deprecated) side by side
python -m ecapi build --out site && python -m ecapi verify --out site

# 6. Commit archive/v1/, contracts/v2.json, api-versions.json and the code together, then push
```

Notes:

- `archive/v1/` is a few thousand files (~15–30 MB). It's committed once and never changes again.
- The frozen version stops receiving data. Its `deprecation.data_frozen_at` tells clients how old it is.
- To retire a version after its sunset date, delete `archive/vN/`, remove it from
  `api-versions.json`, and push. Clients then get 404s, so give a sunset date in advance.
- Only bump for breaking changes. A new faculty, source, type or field goes into the current
  version (then run `ecapi contract --write`).

## What `verify` checks

- Every item in `all.json` passes the schema, ids are unique, and each `item/{id}.json` matches.
- **Every** filter file exists and contains exactly what a separate, plain predicate in
  `verify.py` says it should, in the same order. That's 4,200 files cross-checked on every deploy.
- No stray filter files exist, and the subfaculty tree in `info.json` matches what's declared and used.
- `tags.json` counts and every `tag/{tag}.json` are correct.
- Every example URL in `v1/index.json` actually exists.
- Each source meets its health floor.

## GitHub Actions (`.github/workflows/update.yml`)

| Trigger | Scrapes? | Then |
|---|---|---|
| Mondays 09:17 UTC | yes (data is a week old, so every source) | commit changed snapshots, then test, build, verify, deploy |
| Manual "Run workflow" | sources older than 3 days (tick **force** for all) | same |
| Push to `main` | no | test, build, verify, deploy from committed snapshots |

One-time setup: **Settings → Pages → Source: GitHub Actions**, then run the workflow once by hand.

- Commits made by the workflow don't re-trigger it (GitHub's rule for `GITHUB_TOKEN` pushes), so
  there's no loop.
- GitHub disables scheduled workflows after 60 days without repository activity. The weekly
  snapshot commits normally prevent that, but if every source is unchanged for two months you'll
  get an email. Click "Enable workflow" to restart it.
- A failed `verify` means no deploy. The previous site stays live, so a broken scraper never
  publishes bad data.

## Adding a source or a school

**New source for Queen's:**

1. Create `src/ecapi/sources/queens_<name>.py` with `SOURCE_ID`, `SOURCE_NAME`,
   `fetch(client) -> raw dict` and `parse(raw) -> list[record]`. Copy the record shape from an
   existing source.
2. Check the site's robots.txt and terms first. Use `client.get()`, which enforces robots.txt.
   Don't collect personal data (executive names, personal emails).
3. Register it in `SOURCES` in `src/ecapi/schools/queens.py`, map it to a faculty and subfaculty
   in `build_items`, list it under that faculty in `SCHOOL_INFO`, and add a health floor.
4. Add a small HTML/JSON fixture to `tests/conftest.py` and parser tests.
5. Run `python -m ecapi scrape --source <id>`, then build and verify.

**New school:** create `src/ecapi/schools/<school>.py` exposing `SCHOOL`, `SCHOOL_INFO`,
`SOURCES`, `build_items(snapshots, overrides)` and `MIN_ITEMS_PER_SOURCE`, then add it to
`src/ecapi/schools/__init__.py`. Everything else (endpoints, verify, docs page) is generic.

**Faculties with no source yet** (Queen's Education, Law, Graduate, and Nursing/Medicine/Rehab
inside Health Sciences): these are candidates whenever their student societies publish a club list.

## Ground rules (keep these)

- Public pages only. Obey robots.txt including crawl-delay. Send an honest User-Agent (it includes
  the repo URL automatically in Actions).
- No personal data. Club-level links only.
- Unknown is `null`. Never fill a field with a guess; use an override with a note instead.
- Every item links back to its `listing_url`.

## Repo map

```
src/ecapi/
  cli.py            scrape / build / verify commands
  http.py           polite client: robots.txt, crawl-delay, retries, User-Agent
  schema.py         the Item model (pydantic) and API_VERSION
  contract.py       contracts/v{N}.json: records the public contract, detects breaking changes
  versions.py       api-versions.json registry, `freeze`, serving deprecated versions
  infer.py          text rules for hours, meetings, first-year, tags
  build.py          writes every endpoint
  verify.py         independent re-check of the built site
  store.py          snapshot + overrides I/O
  docs.py           generates docs/ from the code (`ecapi docs`; CI runs `--check`)
  sources/          one module per source
  schools/          one module per school (mapping, merging, overrides)
  static/index.html docs page with a live query builder
contracts/v1.json   public contract of v1 (breaking changes vs this fail CI)
api-versions.json   which API versions exist / are current / deprecated
archive/            frozen deprecated versions (empty until the first breaking change)
data/queens/raw/    committed source snapshots
data/queens/overrides.yaml
docs/               generated public reference (do not edit by hand)
tests/              parser, inference, build and verify tests (with fixtures)
```
