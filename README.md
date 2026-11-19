# Extracurricular API

A free JSON API of university extracurriculars: clubs, design teams, sports clubs, conferences,
competitions and committees. The data comes from each school's own public directories, and we
attempt to refresh it every week.

There's no API key, no sign-up and no rate limit. Every endpoint is a plain JSON file you can
`fetch()`, from a browser or a server, and CORS is open.

```js
const BASE = "https://<owner>.github.io/extracurricular-api/";
const res = await fetch(BASE + "v1/queens/filter/fac-engineering/sub-any/type-design-team/app-any/first-friendly.json");
const { count, items } = await res.json();
```

**Schools covered:** Queen's University (`queens`).

## Documentation

Full reference in [`docs/`](docs/README.md):

| Page | What's in it |
|---|---|
| [Endpoints](docs/endpoints.md) | Every URL you can request |
| [Filters](docs/filters.md) | The five filter segments and every value they accept |
| [Responses](docs/responses.md) | The envelope around every response, endpoint by endpoint |
| [Fields](docs/fields.md) | Every field of an activity: type, allowed values, meaning |
| [Versions](docs/versions.md) | Versioning, deprecation, and every version so far |
| [Queen's](docs/schools/queens.md) | Faculties, subfaculties, sources and their URLs |

Those pages are generated from the same code that builds the JSON, so they always match the API.
The rest of this page is a quick tour.

---

## Endpoints

| What you want | Endpoint |
|---|---|
| Which schools are covered | `v1/schools.json` |
| A school's faculties, data sources, freshness and every valid filter value | `v1/{school}/info.json` |
| Every activity at a school | `v1/{school}/all.json` |
| One activity | `v1/{school}/item/{id}.json` |
| Activities matching filters | `v1/{school}/filter/fac-…/sub-…/type-…/app-…/first-….json` |
| Every tag, with counts | `v1/{school}/tags.json` |
| Activities with one tag | `v1/{school}/tag/{tag}.json` |
| This list, as JSON | `v1/index.json` |
| Every API version and which is current | `versions.json` (no version prefix) |

A URL that doesn't exist returns HTTP 404. Use `info.json` to see which values are valid.

### `filter`: the main endpoint

```
v1/{school}/filter/ fac-{faculty} / sub-{subfaculty} / type-{type} / app-{status} / first-{status} .json
```

Always give all five segments, in this order. Each segment names what it filters, and the
`-any` value means "don't filter on this".

| # | Segment | Values | Meaning |
|---|---|---|---|
| 1 | `fac-` faculty | `fac-any` | every faculty |
| | | `fac-general` | open to students from **any** faculty (student-government clubs, rec clubs) |
| | | `fac-arts-science`, `fac-business`, `fac-engineering`, `fac-health-sciences`, `fac-education`, `fac-law`, `fac-graduate` | run by or for that faculty |
| 2 | `sub-` subfaculty | `sub-any` | the whole faculty |
| | | `sub-computing`, `sub-commerce`, `sub-civil-engineering`, … | one programme inside the chosen faculty (see `info.json → faculties`) |
| 3 | `type-` | `type-any` | every kind |
| | | `type-club` | student club |
| | | `type-team` | sports or performance team |
| | | `type-design-team` | engineering design team building a project for competition |
| | | `type-discipline-club` | club for one engineering discipline |
| | | `type-committee` | student-government committee or operational team |
| | | `type-conference` | student-run conference |
| | | `type-competition` | student-run competition |
| 4 | `app-` applications | `app-open` | accepting applications right now (**includes** `app-rolling`) |
| | | `app-rolling` | always open: join or drop by any time, no application window |
| | | `app-closed` | not accepting right now |
| | | `app-unknown` | the source doesn't say |
| | | `app-any` | don't filter |
| 5 | `first-` first-years | `first-focused` | made specifically for first-year students |
| | | `first-friendly` | first-years can join (**includes** `first-focused`) |
| | | `first-no` | not open to first-years |
| | | `first-unknown` | the source doesn't say |
| | | `first-any` | don't filter |

A `sub-` value only exists under its own faculty. `fac-engineering/sub-civil-engineering` works,
but `fac-any/sub-civil-engineering` and `fac-business/sub-civil-engineering` return 404.

### Examples (Queen's)

| Question | URL |
|---|---|
| All engineering design teams | `v1/queens/filter/fac-engineering/sub-any/type-design-team/app-any/first-any.json` |
| Anything accepting applications that a first-year can join | `v1/queens/filter/fac-any/sub-any/type-any/app-open/first-friendly.json` |
| Things you can just show up to, any time | `v1/queens/filter/fac-any/sub-any/type-any/app-rolling/first-any.json` |
| Things made for first-years | `v1/queens/filter/fac-any/sub-any/type-any/app-any/first-focused.json` |
| Commerce conferences | `v1/queens/filter/fac-business/sub-commerce/type-conference/app-any/first-any.json` |
| Computing clubs | `v1/queens/filter/fac-arts-science/sub-computing/type-any/app-any/first-any.json` |
| Clubs open to every faculty | `v1/queens/filter/fac-general/sub-any/type-club/app-any/first-any.json` |
| Civil engineering | `v1/queens/filter/fac-engineering/sub-civil-engineering/type-any/app-any/first-any.json` |
| One team | `v1/queens/item/engsoc-qset.json` |
| Everything tagged robotics | `v1/queens/tag/robotics.json` |

### Filtering on numbers

Hours per week and meetings per week aren't URL filters, but every activity includes them as
numbers. Fetch any list and filter it in your own code:

```js
const { items } = await (await fetch(BASE + "v1/queens/all.json")).json();
const light = items.filter(i => (i.time_commitment.hours_per_week_max ?? Infinity) <= 3);
const weekly = items.filter(i => i.meetings.per_week === 1);
```

---

## Responses

Every response is an object with the same envelope:

```jsonc
{
  "api_version": "1",
  "deprecated": false,                          // true only on a replaced version (see below)
  "school": "queens",
  "data_as_of": "2026-11-19T06:31:56+00:00",   // when the newest source was collected
  "endpoint": "filter",                         // all | item | filter | tag | tags | info
  "query": { "faculty": "fac-engineering", "subfaculty": "sub-any", "type": "type-design-team",
             "app": "app-any", "first": "first-friendly" },   // filter and tag only
  "count": 3,
  "items": [ /* activities */ ]                 // "item" for the item endpoint
}
```

### An activity

```jsonc
{
  "id": "engsoc-qset",                       // stable, use it with item/{id}.json
  "api_version": "1",
  "school": "queens",
  "name": "Queen's Space Engineering Team (QSET)",
  "type": "design-team",
  "faculty": "engineering",                  // "general" = open to any faculty
  "subfaculty": null,                        // e.g. "civil-engineering", "computing", "commerce"
  "applications_open": null,                 // true | false | null (unknown)
  "application_deadline": null,              // "YYYY-MM-DD" | "rolling" (always open) | null
  "eligibility": {
    "first_year": "friendly",                // "focused" | "friendly" | "no" | null
    "first_year_friendly": true,             // same thing as a boolean (focused counts as true)
    "years": null,                           // undergraduate years explicitly allowed, e.g. [1, 2, 3, 4]
    "graduate_students": null                // true when it's a graduate-student group
  },
  "time_commitment": { "hours_per_week_min": null, "hours_per_week_max": null },
  "meetings": { "per_week": null, "frequency": null },
  //   per_week: 0.25 monthly, 0.5 biweekly, 1 weekly, 2 twice a week …
  //   frequency: "monthly" | "biweekly" | "weekly" | "2x-weekly" | "3x-weekly" | …
  "tags": ["aerospace", "competition", "design-team", "research"],
  "description": "QSET is a group of …",
  "listing_url": "https://www.engsoc.queensu.ca/get-involved/design-teams/",   // the original listing
  "apply_url": "https://qset.ca/",           // where to apply or learn more
  "links": { "website": "https://qset.ca/", "instagram": "https://www.instagram.com/qset/" },
  "source": { "id": "queens-engsoc", "name": "Queen's Engineering Society", "url": "https://www.engsoc.queensu.ca" },
  "also_listed_in": [],                      // other directories that list the same activity
  "source_updated_at": null,
  "provenance": {
    "eligibility.first_year": { "method": "inferred", "evidence": "…no experience is required to join…" }
  }
}
```

### `null` means unknown

Nothing is guessed. If a directory doesn't say whether a club is first-year friendly or how
often it meets, the field is `null` and filters treat it as `app-unknown` / `first-unknown`.
Most directories don't list hours or meeting times, so expect many `null`s there.

### `provenance`: how each value was decided

Any value not copied directly from the listing has an entry in `provenance`:

| `method` | Meaning |
|---|---|
| `source` | stated by an official source, e.g. an active recruitment posting |
| `inferred` | read from the listing's text by a fixed rule; `evidence` quotes the words it matched |
| `derived` | follows from which directory it was listed in (e.g. EngSoc means faculty `engineering`) |
| `override` | checked and set by a maintainer; `evidence` says where the information came from |

If an `inferred` value looks wrong, the `evidence` field shows exactly why it was set.

---

## Where the data comes from (Queen's)

| Faculty | Source |
|---|---|
| General (any faculty) | [AMS Club Directory](https://www.myams.org/clubs/club-directory/), [Athletics & Recreation clubs](https://rec.gogaelsgo.com/sports/2013/7/31/Clubs_0731135902.aspx) |
| Engineering | [Engineering Society](https://www.engsoc.queensu.ca/get-involved/): design teams, clubs, discipline clubs, plus its hiring portal for open applications |
| Arts & Science → Computing | [COMPSA Computing Clubs Roundtable](https://compsa.ca/ccr) |
| Business → Commerce | [Smith School of Business / ComSoc](https://smith.queensu.ca/bcom/experience/life-outside-class.php) |
| Health Sciences → BHSc | [Health Sciences Society](https://www.queenshss.ca/hss-ratified-clubs) |
| Education, Law, Graduate | No public directory yet. The endpoints exist and currently return empty lists |

`info.json → sources` shows when each source was last collected. If a source's site was down,
it shows that the data came from the Internet Archive and the date of that copy.

When one club appears in two directories, it's returned once. The more specific listing is the
main one, and the other goes in `also_listed_in`.

## Versions and deprecation

Every path starts with an API version (`v1/…`). Within a version, URLs, filter values and fields
are only ever **added**, never removed, renamed or changed in type. Any change that would break
your code ships as a new version instead.

When a new version comes out, the old one **keeps working** but stops updating:

- Its data is frozen at the moment it was replaced.
- Every response in it has `"deprecated": true` and a `deprecation` block:

```jsonc
{
  "api_version": "1",
  "deprecated": true,
  "deprecation": {
    "since": "2027-01-10",
    "successor": "v2",
    "successor_index": "v2/index.json",
    "sunset": "2027-09-01",                 // date it may be removed, or null if none is set
    "data_frozen_at": "2027-01-06T09:40:12+00:00",
    "message": "API v1 is deprecated and its data is frozen as of …. Move to v2: see v2/index.json."
  },
  "school": "queens",
  …
}
```

Responses from the current version always include `"deprecated": false`, so one check works
everywhere:

```js
const data = await (await fetch(url)).json();
if (data.deprecated) console.warn(data.deprecation.message);
```

`versions.json` at the site root lists every version, which one is current, and the
deprecation details for the others. It's the only path without a version prefix, and it never moves.

## Good to know

- **Freshness:** we attempt to collect every source weekly, but a collection can fail (a site is
  down or changes its page). When that happens the last good copy is kept, so some data may be
  older than a week. `data_as_of` in any response, and `info.json → sources[].fetched_at`, show
  how fresh it actually is.
- **Accuracy:** descriptions and links are the clubs' own, as published. Always confirm deadlines
  and requirements on the `listing_url` before relying on them.
- **Privacy:** the site and API collect nothing about you: no cookies, analytics or tracking. The
  data is club-level only, with no executive names, personal emails or photos. See the
  [privacy page](src/ecapi/static/privacy.html) (published as `privacy.html` on the site).
- **Something wrong, or should something be removed?** Open an issue on this repository with the
  activity `id`. Removed items stay out of future updates.

## License

The code is MIT licensed (see [LICENSE](LICENSE)). The listings (names, descriptions, links)
belong to the clubs and the directories they were collected from. This API republishes publicly
posted information for discovery, and every item links back to its original listing.
