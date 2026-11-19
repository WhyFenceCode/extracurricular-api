"""Data model for every item the API serves.

Every field that is not taken verbatim from a source carries a provenance entry,
so consumers (and reviewers) can tell scraped facts from inferred guesses.
Unknown is always ``null`` -- the builder never invents a value.

Field ``description``s here are the public documentation: ``ecapi docs`` turns them
into docs/fields.md, so write them for API users.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

API_VERSION = "1"


class ItemType(str, Enum):
    club = "club"
    team = "team"
    design_team = "design-team"
    discipline_club = "discipline-club"
    committee = "committee"
    conference = "conference"
    competition = "competition"


class Method(str, Enum):
    source = "source"  # copied from the official listing
    inferred = "inferred"  # extracted from listing text by a rule (see evidence)
    override = "override"  # set by a human in data/<school>/overrides.yaml
    derived = "derived"  # follows mechanically from which listing the item came from


METHOD_DOCS = {
    "source": "Stated by an official source, e.g. an active recruitment posting.",
    "inferred": "Read from the listing's own text by a fixed rule. `evidence` quotes the words that matched.",
    "derived": "Follows from which directory the activity was listed in (e.g. EngSoc means faculty `engineering`).",
    "override": "Checked and set by a maintainer. `evidence` says where the information came from.",
}


class Provenance(BaseModel):
    model_config = ConfigDict(extra="forbid")
    method: Method = Field(description="How the value was decided: `source`, `inferred`, `derived` or `override`.")
    evidence: str | None = Field(default=None, description=(
        "Why: the matched listing text, the recruitment posting, or the maintainer's note."))


FirstYear = Literal["focused", "friendly", "no"]


class Eligibility(BaseModel):
    """``first_year`` is the source of truth; ``first_year_friendly`` mirrors it as a boolean."""

    model_config = ConfigDict(extra="forbid")
    first_year: FirstYear | None = Field(default=None, description=(
        "Whether first-year students can take part. `focused`: made specifically for first-years. "
        "`friendly`: first-years can join. `no`: not open to first-years. null: the source doesn't say."))
    first_year_friendly: bool | None = Field(default=None, description=(
        "`first_year` as a boolean: true for focused or friendly, false for no, null when unknown."))
    years: list[int] | None = Field(default=None, description=(
        "Undergraduate years explicitly allowed, e.g. `[1, 2, 3, 4]`. null when the listing doesn't say."))
    graduate_students: bool | None = Field(default=None, description=(
        "true when it is a graduate-student group. null when not stated."))

    def model_post_init(self, _ctx) -> None:
        if self.first_year is not None:
            self.first_year_friendly = self.first_year != "no"
        elif self.first_year_friendly is not None:
            self.first_year = "friendly" if self.first_year_friendly else "no"

    @field_validator("years")
    @classmethod
    def _years(cls, v: list[int] | None) -> list[int] | None:
        if v is None:
            return v
        if any(y < 1 or y > 6 for y in v):
            raise ValueError(f"year out of range: {v}")
        return sorted(set(v))


class TimeCommitment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hours_per_week_min: float | None = Field(default=None, ge=0, le=80, description=(
        "Fewest hours per week expected. A single figure (\"about 4 hours\") sets min and max to the same number."))
    hours_per_week_max: float | None = Field(default=None, ge=0, le=80, description=(
        "Most hours per week expected. null while min is set means \"at least min\"."))

    def model_post_init(self, _ctx) -> None:
        lo, hi = self.hours_per_week_min, self.hours_per_week_max
        if lo is not None and hi is not None and lo > hi:
            raise ValueError(f"hours min {lo} > max {hi}")


FREQUENCY_LABELS: dict[float, str] = {
    0.25: "monthly",
    0.5: "biweekly",
    1.0: "weekly",
    2.0: "2x-weekly",
    3.0: "3x-weekly",
    4.0: "4x-weekly",
    5.0: "daily",
}


class Meetings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    per_week: float | None = Field(default=None, gt=0, le=7, description=(
        "Meetings per week as a number: 0.25 monthly, 0.5 every two weeks, 1 weekly, 2 twice a week, and so on."))
    frequency: str | None = Field(default=None, description=(
        "`per_week` as a label: `monthly`, `biweekly`, `weekly`, `2x-weekly`, `3x-weekly`, `4x-weekly`, `daily`."))

    def model_post_init(self, _ctx) -> None:
        if self.per_week is not None and self.frequency is None:
            self.frequency = FREQUENCY_LABELS.get(float(self.per_week), f"{self.per_week:g}x-weekly")


class Links(BaseModel):
    model_config = ConfigDict(extra="forbid")
    website: str | None = Field(default=None, description="The activity's own website or link page (Linktree etc.).")
    instagram: str | None = Field(default=None, description=(
        "Instagram profile URL, normalised to `https://www.instagram.com/<handle>/`."))


class SourceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(description="Source id, e.g. `queens-engsoc`. Every source is listed in info.json under `sources`.")
    name: str = Field(description="Human-readable name of the directory.")
    url: str = Field(description="The directory's main page.")


class Listing(BaseModel):
    """Another directory that lists the same activity (merged into one item)."""
    model_config = ConfigDict(extra="forbid")
    source: SourceRef = Field(description="The other directory.")
    name: str = Field(description="The name used in that directory (may differ slightly).")
    listing_url: str = Field(description="The listing in that directory.")


class Item(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$", description=(
        "Stable identifier, prefixed by the directory it came from (e.g. `engsoc-qset`, `ams-youreka-kingston`). "
        "Use it with `item/{id}.json`."))
    api_version: Literal["1"] = Field(default=API_VERSION, description="API version this record belongs to.")
    school: str = Field(description="School id, e.g. `queens`.")
    name: str = Field(min_length=1, description="Name as published by the activity's directory.")
    type: ItemType = Field(description="What kind of activity it is. Every value is explained in filters.md.")
    faculty: str = Field(pattern=r"^[a-z0-9-]+$", description=(
        "Faculty that runs it, or `general` when it is open to students from any faculty."))
    subfaculty: str | None = Field(default=None, pattern=r"^[a-z0-9-]+$", description=(
        "Programme or school inside the faculty, e.g. `civil-engineering`, `computing`, `commerce`. "
        "null when it is faculty-wide."))
    applications_open: bool | None = Field(default=None, description=(
        "true while applications are being accepted; false when its recruitment board is active but shows nothing "
        "for it; null when unknown."))
    application_deadline: str | None = Field(default=None, pattern=r"^(?:\d{4}-\d{2}-\d{2}|rolling)$", description=(
        "When applications close: a date as `YYYY-MM-DD`, or `rolling` when it's always open (join or drop by "
        "any time, no application window). null when unknown."))
    eligibility: Eligibility = Field(default_factory=Eligibility, description="Who can join.")
    time_commitment: TimeCommitment = Field(default_factory=TimeCommitment, description="Expected hours per week.")
    meetings: Meetings = Field(default_factory=Meetings, description="How often it meets.")
    tags: list[str] = Field(default_factory=list, description=(
        "Lowercase topic tags: the directory's own categories, the type, the subfaculty, and keyword tags "
        "(robotics, finance…). Every tag is listed in `tags.json`."))
    description: str = Field(default="", description=(
        "The activity's own short description from its listing. Empty when none was published."))
    listing_url: str = Field(description="The original listing this record came from: the page to check before relying on it.")
    apply_url: str | None = Field(default=None, description=(
        "Where to apply or learn more: an open posting if there is one, otherwise the activity's website."))
    links: Links = Field(default_factory=Links, description="Public links for the activity.")
    source: SourceRef = Field(description="The directory this record was collected from.")
    also_listed_in: list[Listing] = Field(default_factory=list, description=(
        "Other directories that list the same activity. It's returned once, with the more specific listing as the main one."))
    source_updated_at: str | None = Field(default=None, description="When the source last changed this listing, if it says.")
    provenance: dict[str, Provenance] = Field(default_factory=dict, description=(
        "For each field not copied directly from the listing, how its value was decided. Keyed by field path, "
        "e.g. `eligibility.first_year`, `meetings`, `applications_open`."))

    def model_post_init(self, _ctx) -> None:
        # "rolling" means always open; a rolling deadline on a closed item is a contradiction.
        if self.application_deadline == "rolling":
            if self.applications_open is False:
                raise ValueError("application_deadline 'rolling' contradicts applications_open false")
            self.applications_open = True

    @field_validator("tags")
    @classmethod
    def _tags(cls, v: list[str]) -> list[str]:
        for t in v:
            if not t or not all(c.isalnum() or c == "-" for c in t) or t != t.lower():
                raise ValueError(f"bad tag {t!r}")
        return sorted(set(v))

    @field_validator("listing_url", "apply_url")
    @classmethod
    def _url(cls, v: str | None) -> str | None:
        if v is not None and not v.startswith(("https://", "http://")):
            raise ValueError(f"not an absolute URL: {v}")
        return v
