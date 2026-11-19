"""Conservative rule-based extraction from listing text.

Each extractor returns ``(value, evidence)`` or ``(None, None)``. Evidence is the
matched snippet so every inferred value can be audited. Rules only fire on
explicit statements ("we meet weekly", "3-5 hours per week", "first-years welcome");
anything vaguer stays unknown.
"""

from __future__ import annotations

import re

_NUM_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
              "nine": 9, "ten": 10, "twelve": 12, "fifteen": 15, "twenty": 20}
_NUM = r"(\d+(?:\.\d+)?|" + "|".join(_NUM_WORDS) + r")"
_PER_WEEK = r"(?:hours?|hrs?)\s*(?:a|per|/|each|every)\s*week"


def _num(s: str) -> float:
    s = s.lower()
    return float(_NUM_WORDS[s]) if s in _NUM_WORDS else float(s)


def _snippet(text: str, m: re.Match, pad: int = 40) -> str:
    a, b = max(0, m.start() - pad), min(len(text), m.end() + pad)
    return ("…" if a else "") + text[a:b].strip() + ("…" if b < len(text) else "")


# --- time commitment -----------------------------------------------------------
_HOURS_RANGE = re.compile(rf"\b{_NUM}\s*(?:-|–|—|to)\s*{_NUM}\+?\s*{_PER_WEEK}", re.I)
_HOURS_SINGLE = re.compile(rf"\b(?:about|around|approximately|~|roughly|up to|at least|minimum of)?\s*{_NUM}\+?\s*{_PER_WEEK}", re.I)


def hours_per_week(text: str) -> tuple[tuple[float | None, float | None] | None, str | None]:
    m = _HOURS_RANGE.search(text)
    if m:
        lo, hi = sorted((_num(m.group(1)), _num(m.group(2))))
        return (lo, hi), _snippet(text, m)
    m = _HOURS_SINGLE.search(text)
    if m:
        v = _num(m.group(1))
        lead = m.group(0).lower()
        if "up to" in lead:
            return (None, v), _snippet(text, m)
        if "at least" in lead or "minimum" in lead or "+" in m.group(0):
            return (v, None), _snippet(text, m)
        return (v, v), _snippet(text, m)
    return None, None


# --- meeting frequency -----------------------------------------------------------
_DAYS = r"(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)s?"
_MEET = r"(?:meet(?:s|ings?)?|practi[cs]es?|sessions?|gather(?:ings?)?|workshops?)"
_FREQ_RULES: list[tuple[float, re.Pattern]] = [
    (3.0, re.compile(rf"\b(?:three times|3\s*x|3 times|thrice)\s*(?:a|per|each)\s*week", re.I)),
    (2.0, re.compile(rf"\b(?:twice|two times|2\s*x|2 times)\s*(?:a|per|each)\s*week", re.I)),
    (2.0, re.compile(rf"\b(?:semi-?weekly)\b", re.I)),
    (0.5, re.compile(rf"\b(?:bi-?weekly|every (?:other|two|2) weeks?|fortnightly)\b", re.I)),
    (0.25, re.compile(rf"\b{_MEET}\b[^.]{{0,40}}\b(?:monthly|once a month|every month)\b|\b(?:monthly|once a month)\s+{_MEET}\b", re.I)),
    # (?<![\w-]) so "bi-weekly" / "semi-weekly" never also count as weekly
    (1.0, re.compile(rf"\b{_MEET}\b[^.]{{0,40}}(?<![\w-])(?:weekly|once a week|every week|each week|every {_DAYS})\b", re.I)),
    (1.0, re.compile(rf"(?<![\w-])(?:weekly|once a week)\s+{_MEET}\b", re.I)),
]


def meetings_per_week(text: str) -> tuple[float | None, str | None]:
    """When a listing states several cadences ("weekly meetings and monthly socials"),
    the most frequent one is the regular meeting, so the highest value wins."""
    best: tuple[float, str] | None = None
    for value, rx in _FREQ_RULES:
        m = rx.search(text)
        if m and (best is None or value > best[0]):
            best = (value, _snippet(text, m))
    return best if best else (None, None)


# --- eligibility -----------------------------------------------------------------
_FY_YES = [
    re.compile(r"\bfirst[- ]?years?\b[^.]{0,60}\b(?:welcome|encouraged|eligible|can join|are invited|may apply|positions)", re.I),
    re.compile(r"\b(?:welcom\w*|open to|encourag\w*|invit\w*)\b[^.]{0,40}\bfirst[- ]?years?\b", re.I),
    re.compile(r"\b(?:students|members|anyone) (?:of|from|in) all (?:years|levels|experience levels|years of study|skill levels)\b", re.I),
    re.compile(r"\ball (?:years|years of study|experience levels|skill levels)\b[^.]{0,30}\bwelcome\b", re.I),
    re.compile(r"\bno (?:prior )?experience (?:is )?(?:required|necessary|needed)\b", re.I),
    re.compile(r"\bregardless of (?:year|experience)\b", re.I),
    # "no experience needed" in other words: open to every skill level, beginners included
    re.compile(r"\ball (?:skill|experience) levels\b", re.I),
    re.compile(r"\b(?:open to|for|caters to|welcom\w*)\b[^.]{0,25}\ball levels\b(?! of fitness)", re.I),
    re.compile(r"\bbeginners?\b[^.]{0,20}\b(?:to|and) (?:intermediate|advanced|experienced)\b"
               r"|\bbeginner[- ]friendly\b|\b(?:experienced \w+|both) and beginners\b|\bexperienced \w+ and beginners\b", re.I),
]
_FY_NO = [
    re.compile(r"\b(?:upper[- ]?year|senior)\s+(?:students\s+)?only\b", re.I),
    re.compile(r"\bnot open to first[- ]?years?\b", re.I),
    re.compile(r"\bgraduate students only\b", re.I),
]
_ALL_YEARS = re.compile(r"\b(?:all years|students (?:of|from|in) all years(?: of study)?)\b", re.I)
_GRAD = re.compile(r"\b(?:graduate students?|grad students?|master'?s|ph\.?d\.?|doctoral)\b", re.I)


_FY_FOCUSED = [
    re.compile(r"\b(?:for|exclusively for|designed for|aimed at|dedicated to|by and for)\s+(?:incoming\s+|new\s+)?first[- ]?years?(?: students)?\b", re.I),
    re.compile(r"\bfirst[- ]?years?\s+(?:students\s+)?(?:only|exclusively)\b", re.I),
    re.compile(r"\bfirst[- ]?year\s+(?:council|representatives?|reps?|committee|executive|conference|mentorship program|program(?:me)?)\b", re.I),
    re.compile(r"\b(?:transition|adjust\w*) to (?:university|campus|queen's)\b", re.I),
]


def first_year_status(text: str) -> tuple[str | None, str | None]:
    """'focused' | 'friendly' | 'no' | None, with evidence."""
    for rx in _FY_NO:
        m = rx.search(text)
        if m:
            return "no", _snippet(text, m)
    for rx in _FY_FOCUSED:
        m = rx.search(text)
        if m:
            return "focused", _snippet(text, m)
    v, ev = first_year_friendly(text)
    return ("friendly" if v else None), ev


def first_year_friendly(text: str) -> tuple[bool | None, str | None]:
    for rx in _FY_NO:
        m = rx.search(text)
        if m:
            return False, _snippet(text, m)
    for rx in _FY_YES:
        m = rx.search(text)
        if m:
            return True, _snippet(text, m)
    return None, None


def explicit_years(text: str) -> tuple[list[int] | None, str | None]:
    m = _ALL_YEARS.search(text)
    if m:
        return [1, 2, 3, 4], _snippet(text, m)
    return None, None


def mentions_graduate_students(text: str) -> tuple[bool | None, str | None]:
    m = _GRAD.search(text)
    if m:
        return True, _snippet(text, m)
    return None, None


# --- applications ----------------------------------------------------------------
ROLLING = "rolling"  # application_deadline value: always open, join whenever

# Explicitly closed. Checked first.
_APP_CLOSED = [
    re.compile(r"\b(?:applications?|recruitment|hiring|registration|sign[- ]?ups?) (?:are |is |has )?(?:now |currently )?(?:closed|over|ended)\b", re.I),
    re.compile(r"\bnot (?:currently |presently )?(?:recruiting|hiring|accepting (?:new )?(?:members|applications))\b", re.I),
]
# Always open: you can show up or join whenever, with no application window.
_APP_ROLLING = [
    re.compile(r"\b(?:join|sign up|register|come|attend|drop (?:in|by)|stop by)\b[^.]{0,30}\b(?:any ?time|at any time|year[- ]round|all year(?: long)?|whenever|any week)\b", re.I),
    re.compile(r"\baccept(?:s|ing)? (?:new )?(?:members|applications) (?:year[- ]round|all year|at any time|anytime|on a rolling basis)\b", re.I),
    re.compile(r"\b(?:rolling (?:basis|admissions?|applications?|membership))\b", re.I),
    re.compile(r"\bdrop[- ]in(?:s| sessions?| nights?| hours?)?\b|\bdrop by\b|\bstop by\b", re.I),
    re.compile(r"\bopen (?:invit(?:e|ation)s?|door|membership)\b", re.I),
    re.compile(r"\bno (?:applications?|tryouts?|try-outs?|auditions?|sign[- ]ups?) (?:is |are )?(?:required|needed|necessary)\b|\bno (?:tryouts?|try-outs?|auditions?)\b", re.I),
    re.compile(r"\b(?:everyone|anyone|all) (?:is |are )?(?:always )?welcome\b", re.I),
]
# Open now: an invitation to join, but nothing says it's year-round.
_APP_OPEN = [
    re.compile(r"\b(?:applications? (?:are |is )?(?:now )?open|now (?:recruiting|hiring|accepting (?:applications|new members)))\b", re.I),
    re.compile(r"\bjoin us\b|\bcome (?:check us out|join us|out and join)\b", re.I),
    re.compile(r"\bjoin (?:our|the) (?:team|club|community|group|family|crew|society|association)\b", re.I),
    re.compile(r"\bnew members (?:are )?(?:always )?welcome\b|\bwelcom\w* new members\b", re.I),
    re.compile(r"\b(?:join|sign up|become a member)\b[^.]{0,20}\b(?:today|now)\b", re.I),
    re.compile(r"\bopen to (?:everyone|anyone|the public|all(?: [\w']+)? students)\b", re.I),
]


def application_status(text: str) -> tuple[bool | None, str | None, str | None]:
    """(applications_open, application_deadline, evidence).

    closed  -> (False, None, …)        e.g. "recruitment is closed"
    rolling -> (True, "rolling", …)    e.g. "drop by any week", "no tryouts", "everyone welcome"
    open    -> (True, None, …)         e.g. "join us", "join our team"
    unknown -> (None, None, None)
    """
    for rx in _APP_CLOSED:
        if m := rx.search(text):
            return False, None, _snippet(text, m)
    for rx in _APP_ROLLING:
        if m := rx.search(text):
            return True, ROLLING, _snippet(text, m)
    for rx in _APP_OPEN:
        if m := rx.search(text):
            return True, None, _snippet(text, m)
    return None, None, None


def applications_open(text: str) -> tuple[bool | None, str | None]:
    v, _deadline, ev = application_status(text)
    return v, ev


# --- tags --------------------------------------------------------------------------
TAG_RULES: dict[str, re.Pattern] = {
    "robotics": re.compile(r"\brobot(?:s|ics)?\b", re.I),
    "competition": re.compile(r"\bcompet(?:e|es|ition|itions|ing|itive)\b", re.I),
    "research": re.compile(r"\bresearch\b", re.I),
    "volunteering": re.compile(r"\bvolunteer\w*|\bcharit\w*|\bfundrais\w*|\bdonat\w*", re.I),
    "sustainability": re.compile(r"\bsustainab\w*|\bclimate\b|\benvironmental\w*|\bsolar\b|\brenewable\b|\becolog\w*|\bclean energy\b", re.I),
    "software": re.compile(r"\bsoftware\b|\bcoding\b|\b(?:computer|web|mobile) programming\b|\bprogramming languages?\b|\bhackathon\w*|\b(?:app|web|mobile) development\b", re.I),
    "ai": re.compile(r"\bAI\b|\b[Aa]rtificial [Ii]ntelligence\b|\b[Mm]achine [Ll]earning\b"),
    "aerospace": re.compile(r"\bspace (?:science|technology|engineering|exploration|industry|systems)\b|\baerospace\b|\baero design\b|\baircraft\b|\brockets?\b|\brocketry\b|\bsatellites?\b|\bcubesats?\b", re.I),
    "automotive": re.compile(r"\bvehicle\w*|\brace car\b|\bcar team\b|\bbaja\b|\bformula\b", re.I),
    "biomedical": re.compile(r"\bbiomedic\w*|\bmedical\b|\bhealthcare\b|\bbiotech\w*|\bgenetic\w*", re.I),
    "outreach": re.compile(r"\boutreach\b|\bmentor\w*|\btutor\w*", re.I),
    "networking": re.compile(r"\bnetworking\b|\bcareer\w*|\bprofessional development\b", re.I),
    "cultural": re.compile(r"\bcultur\w*|\bheritage\b|\bdiaspora\b", re.I),
    "faith": re.compile(r"\bfaith\b|\bchristian\w*|\bmuslim\w*|\bjewish\b|\bhindu\w*|\bsikh\w*|\bbuddhis\w*|\bcatholic\w*", re.I),
    "music": re.compile(r"\bmusic\w*|\bchoir\b|\ba cappella\b|\bsinging\b|\borchestra\b", re.I),
    "dance": re.compile(r"\bdanc\w*", re.I),
    "theatre": re.compile(r"\btheat(?:re|er)\w*|\bmusical\b|\bimprov\b|\bdrama\b", re.I),
    "debate": re.compile(r"\bdebat\w*|\bmodel (?:un|united nations)\b", re.I),
    "finance": re.compile(r"\bfinance\b|\bfinancial (?:markets?|literacy|services|analysis)\b|\binvest(?:ing|ment|ments|or|ors)\b|\btrading\b|\bconsulting\b", re.I),
    "entrepreneurship": re.compile(r"\bentrepreneur\w*|\bstartups?\b|\bventure\w*", re.I),
    "advocacy": re.compile(r"\badvoca\w*|\bsocial justice\b|\bactivism\b", re.I),
    "equity": re.compile(r"\bequity\b|\bdiversity\b|\bwomen in\b|\b2SLGBTQ\w*|\bLGBTQ\w*|\bqueer\b", re.I),
    "gaming": re.compile(r"\bvideo games?\b|\besports?\b|\bboard games?\b|\bgaming\b|\bgame (?:dev|development|design)\b|\btabletop\b", re.I),
    "writing": re.compile(r"\bjournal\b|\bmagazine\b|\bpublications?\b|\bcreative writing\b|\bwriters?\b|\bpoetry\b", re.I),
    "outdoors": re.compile(r"\boutdoor\w*|\bhiking\b|\bcamping\b|\bclimb\w*", re.I),
}


def keyword_tags(text: str) -> list[str]:
    return sorted(t for t, rx in TAG_RULES.items() if rx.search(text))
