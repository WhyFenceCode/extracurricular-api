import pytest

from ecapi import infer


@pytest.mark.parametrize("text,expected", [
    ("Expect 3-5 hours per week during build season.", (3, 5)),
    ("It takes about 4 hours a week.", (4, 4)),
    ("Members commit two to three hours per week.", (2, 3)),
    ("Up to 10 hrs/week near competition.", (None, 10)),
    ("At least 6 hours per week.", (6, None)),
    ("10+ hours per week", (10, None)),
    ("We had 300 members last year.", None),
    ("Open 24 hours.", None),
])
def test_hours(text, expected):
    assert infer.hours_per_week(text)[0] == expected


@pytest.mark.parametrize("text,expected", [
    ("We meet weekly on Thursdays.", 1.0),
    ("Weekly meetings in Mitchell Hall.", 1.0),
    ("General meetings happen every Monday.", 1.0),
    ("Practices twice a week.", 2.0),
    ("We train 3x per week.", 3.0),
    ("Meetings are bi-weekly.", 0.5),
    ("We get together every other week.", 0.5),
    ("Monthly socials and meetings once a month.", 0.25),
    ("Read our weekly newsletter.", None),  # newsletter is not a meeting
    ("We host weekly meetings on weekdays and longer monthly meetings on weekends.", 1.0),  # most frequent wins
    ("Monthly socials, and we meet twice a week for practice.", 2.0),
    ("A welcoming community.", None),
])
def test_meetings(text, expected):
    assert infer.meetings_per_week(text)[0] == expected


@pytest.mark.parametrize("text,expected", [
    ("First-years are welcome to apply!", True),
    ("We encourage first year students to join.", True),
    ("Open to students of all years.", True),
    ("No prior experience required.", True),
    ("no experience is required to join", True),
    ("Open to all experience levels, our sessions focus on speaking.", True),
    ("Our club is open to all skill levels, from beginners to experienced.", True),
    ("Regular clinics for all levels - beginner to advanced.", True),
    ("Caters to both beginner and intermediate runners.", True),
    ("Both experienced archers and beginners.", True),
    ("Anyone is welcome, with or without training and all levels of fitness.", None),
    ("Upper-year students only.", False),
    ("Not open to first-years.", False),
    ("We build rockets.", None),
    ("Our first year as a club was 2019.", None),
])
def test_first_year(text, expected):
    assert infer.first_year_friendly(text)[0] is expected


@pytest.mark.parametrize("text,expected", [
    ("First Year Council. Represents the class.", "focused"),
    ("A mentorship program for first-year students.", "focused"),
    ("Open to first-year students only.", "focused"),
    ("Helping new students transition to university.", "focused"),
    ("First-years are welcome to apply!", "friendly"),
    ("No experience required.", "friendly"),
    ("Upper-year students only.", "no"),
    ("We build bridges.", None),
])
def test_first_year_status(text, expected):
    assert infer.first_year_status(text)[0] == expected


@pytest.mark.parametrize("text,open_,deadline", [
    # rolling: always open
    ("Drop by any week, no sign-up needed.", True, "rolling"),
    ("Weekly drop-in sessions at the ARC.", True, "rolling"),
    ("Stop by our booth!", True, "rolling"),
    ("Open invitation to all students.", True, "rolling"),
    ("We accept new members year-round.", True, "rolling"),
    ("Join anytime during the year.", True, "rolling"),
    ("No tryouts, just show up.", True, "rolling"),
    ("Everyone is welcome!", True, "rolling"),
    ("Applications accepted on a rolling basis.", True, "rolling"),
    # open now, no window stated
    ("Join us for weekly practices!", True, None),
    ("Join our team and build rockets.", True, None),
    ("New members always welcome.", True, None),
    ("Applications are now open.", True, None),
    ("Open to all Queen's students.", True, None),
    ("Sign up today!", True, None),
    # closed beats everything
    ("Recruitment is closed. Everyone welcome at events.", False, None),
    ("We are not currently recruiting.", False, None),
    # nothing said
    ("We build bridges out of popsicle sticks.", None, None),
    ("Students who joined last year won awards.", None, None),
    ("Open to all experience levels.", None, None),  # that's eligibility, not an invitation
])
def test_application_status(text, open_, deadline):
    v, d, ev = infer.application_status(text)
    assert (v, d) == (open_, deadline)
    assert (ev is None) == (open_ is None)


def test_evidence_is_from_text():
    text = "Lots of things. We meet weekly in the ILC. More things."
    v, ev = infer.meetings_per_week(text)
    assert v == 1.0 and "meet weekly" in ev


@pytest.mark.parametrize("text,tag,present", [
    ("Provide a welcoming space for students.", "aerospace", False),
    ("Queen's Space Engineering Team builds satellites.", "aerospace", True),
    ("Provide an environment where students grow.", "sustainability", False),
    ("Environmental advocacy and climate action.", "sustainability", True),
    ("Movie and Games Night.", "gaming", False),
    ("Competitive esports and video games.", "gaming", True),
    ("From mechanical to chemical and financial.", "finance", False),
    ("Student-run investment fund.", "finance", True),
    ("An inclusive environment.", "equity", False),
    ("Singapore students association", "music", False),
    ("Inclusive programming in a supportive environment.", "software", False),
    ("Hands-on web development workshops.", "software", True),
    ("Practical self defence and awareness.", "advocacy", False),
    ("We advocate for accessible healthcare.", "advocacy", True),
])
def test_tag_rules(text, tag, present):
    assert (tag in infer.keyword_tags(text)) is present
