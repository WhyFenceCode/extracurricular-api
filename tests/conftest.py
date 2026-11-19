import copy

import pytest

AMS_RAW = {
    "via": "live",
    "origin_url": "https://www.myams.org/clubs/club-directory/",
    "categories": [
        {"id": 465, "name": "Science &amp; Engineering", "slug": "science-engineering"},
        {"id": 459, "name": "Public Service", "slug": "public-service"},
        {"id": 470, "name": "Government &amp; Politics", "slug": "gov"},
        {"id": 471, "name": "Government and Politics", "slug": "gov-2"},
    ],
    "clubs": [
        {
            "id": 1, "slug": "youreka-kingston", "link": "https://www.myams.org/club/youreka-kingston/",
            "modified": "2025-12-20T21:17:26", "club-categories": [465],
            "title": {"rendered": "Youreka Kingston"},
            "content": {"rendered": '<p><a href="https://www.myams.org/club/youreka-kingston/logo/"><img src="x.png"/></a>'
                        "Empowers youth through hands-on medical research projects. We meet weekly on Tuesdays. "
                        "Students of all years are welcome and no experience is required. "
                        '<strong><a href="https://linktr.ee/yourekakingston?utm_source=ig&amp;fbclid=abc">Learn More</a></strong></p>'},
        },
        {
            "id": 2, "slug": "debate-union", "link": "https://www.myams.org/club/debate-union/",
            "modified": "2025-11-01T10:00:00", "club-categories": [470, 471],
            "title": {"rendered": "Queen&#8217;s Debate Union"},
            "content": {"rendered": "<p>Competitive debating. Practices twice a week, roughly 3-5 hours per week. "
                        "Upper-year students only. "
                        '<a href="https://www.instagram.com/qdu/?hl=en">Instagram</a></p>'},
        },
        {
            "id": 3, "slug": "grad-chess", "link": "https://www.myams.org/club/grad-chess/",
            "modified": None, "club-categories": [],
            "title": {"rendered": "Graduate Students Chess Club"},
            "content": {"rendered": "<p>Casual board games.</p>"},
        },
        {
            "id": 4, "slug": "frosh-council", "link": "https://www.myams.org/club/frosh-council/",
            "modified": None, "club-categories": [],
            "title": {"rendered": "First Year Council"},
            "content": {"rendered": "<p>Represents incoming students and helps them transition to university.</p>"},
        },
    ],
}


def _card(name: str, text: str, site: str | None = "https://team.example/") -> str:
    globe = f'<a class="elementor-icon elementor-social-icon elementor-social-icon-globe" href="{site}">w</a>' if site else ""
    return f"""
    <div class="elementor e-loop-item post-1 teams type-teams status-publish">
      <h2 class="elementor-heading-title elementor-size-default">{name}</h2>
      <div class="elementor-widget-theme-post-excerpt"><div class="elementor-widget-container">{text}</div></div>
      <a class="elementor-icon elementor-social-icon elementor-social-icon-instagram" href="https://www.instagram.com/{name[:4]}/?hl=en">i</a>
      {globe}
      <a class="elementor-icon elementor-social-icon elementor-social-icon-envelope" href="http://team@engsoc.queensu.ca">e</a>
    </div>"""


ENGSOC_RAW = {
    "via": "live",
    "origin_url": "https://www.engsoc.queensu.ca",
    "pages": {
        "design-team": {"via": "live", "url": "https://www.engsoc.queensu.ca/get-involved/design-teams/", "html":
            "<html><body>" + _card("Queen&#8217;s Space Engineering Team (QSET)",
                                   "Rover, robotics and satellite projects. No experience is required to join.")
            + _card("Queen's Baja SAE", "Design and race an off-road vehicle in competition.")
            + _card("Queen's Rocket Engineering Team (QRET)", "Rocketry design team.", None) + "</body></html>"},
        "engsoc-club": {"via": "live", "url": "https://www.engsoc.queensu.ca/get-involved/clubs/", "html":
            _card("Women in Science and Engineering (WiSE)", "Supports women in STEM.") + _card("IT Operations Team", "Runs EngSoc IT.", None)},
        "discipline-club": {"via": "live", "url": "https://www.engsoc.queensu.ca/get-involved/discipline-clubs/", "html":
            _card("Civil DSC", "Represents civil students. We meet bi-weekly.") + _card("Brand New DSC", "New.")},
    },
}

BREEZY_RAW = {"via": "live", "origin_url": "https://x.breezy.hr", "postings": [
    {"name": "QSET Rover Electrical Member", "url": "https://x.breezy.hr/p/abc", "department": "Design Teams",
     "published_date": "2026-09-01"},
]}


SMITH_RAW = {"via": "live", "origin_url": "https://smith.queensu.ca/x", "html": """
<table>
 <tr><th>Business</th><td><ul class="bullets"><li>Queen&#8217;s Marketing Association (QMA)</li></ul></td></tr>
 <tr><th>External: Conferences &amp; Competitions</th><td><ul class="bullets">
   <li>Queen&#8217;s Conference on International Business (QCIB)</li>
   <li>Queen's Commerce Corporate Challenge (Q3C)</li></ul></td></tr>
 <tr><th>External Competitions</th><td><ul><li>Inter-Collegiate Business Competition (ICBC)</li></ul></td></tr>
 <tr><th>Executive Purview</th><td><ul><li>ComSoc Design Team</li></ul></td></tr>
</table>"""}

HSS_RAW = {"via": "live", "origin_url": "https://www.queenshss.ca/hss-ratified-clubs", "html": """
<main>
 <div class="sqs-block"><h2>HSS Ratified Clubs</h2></div>
 <div class="sqs-block"></div>
 <div class="sqs-block"><p>We run anatomy study sessions for first-year students.</p></div>
 <div class="sqs-block"><p>Queen's University Anatomy Club</p></div>
 <div class="sqs-block"><p>Contact Us Instagram : @qu.anatomy</p></div>
 <div class="sqs-block"></div>
 <div class="sqs-block"><p>Advocacy for community health.</p></div>
 <div class="sqs-block"><p>Queen's Health Advocates (QHA)</p></div>
 <div class="sqs-block"><p>Contact Us Instagram : @shared.handle</p></div>
 <div class="sqs-block"><p>Research workshops.</p></div>
 <div class="sqs-block"><p>Research Workshops (HCSRW)</p></div>
 <div class="sqs-block"><p>Contact Us Instagram : @shared.handle</p></div>
 <div class="sqs-block"><p>Forensics.</p></div>
 <div class="sqs-block"><p>Forensic Sciences Association (QFSA)</p></div>
 <div class="sqs-block"><p>Contact Us forensics@clubs.queensu.ca</p></div>
</main>"""}

COMPSA_RAW = {"via": "live", "origin_url": "https://compsa.ca/ccr", "openings": [], "clubs": [
    {"id": "c1", "name": "Queen's Women In Computing", "description": "Community for women in tech.",
     "website_url": "https://qwic.org", "instagram": "https://www.instagram.com/queenswic/#"},
    {"id": "c2", "name": "Queen's Rocket Engineering Team", "description": "Rockets.",
     "website_url": "[PLACEHOLDER URL]", "instagram": None},
]}

REC_RAW = {"via": "live", "origin_url": "https://rec.gogaelsgo.com/x", "html": """
<article>
 <table><tr><td>Sport</td><td>Outdoor Recreation</td></tr>
        <tr><td>Badminton</td><td>Run Club</td></tr>
        <tr><td>Table Tennis</td><td></td></tr></table>
 <hr><p><strong>Badminton Club</strong><br>The club meets once a week for members of all levels!<br>
  <strong>Co-Presidents:</strong> Private Person &amp; Another Person<br>
  <strong>Club Email:</strong> <a href="mailto:qb@queensu.ca">qb@queensu.ca</a><br>
  <a href="https://www.instagram.com/QueensBadmintonClub/">Instagram</a></p>
 <hr><p><strong>Run Club</strong><br>The Run Club caters to beginner and intermediate runners.<br>
  <a href="http://www.runclub.example">Club Website</a></p>
 <hr><p><strong>Women's Football Club</strong><br>The Queen's Women's Football team develops football players.<br></p>
 <hr><p><strong>Table Tennis Club</strong><br>The Queen's Women's Football team develops football players.<br></p>
</article>"""}


def snap(source: str, raw: dict) -> dict:
    return {"source": source, "fetched_at": "2026-11-19T00:00:00+00:00", "via": raw["via"],
            "origin_url": raw["origin_url"], "raw": copy.deepcopy(raw)}


@pytest.fixture
def snapshots():
    return {
        "queens-ams": snap("queens-ams", AMS_RAW),
        "queens-engsoc": snap("queens-engsoc", ENGSOC_RAW),
        "queens-engsoc-breezy": snap("queens-engsoc-breezy", BREEZY_RAW),
        "queens-comsoc": snap("queens-comsoc", SMITH_RAW),
        "queens-hss": snap("queens-hss", HSS_RAW),
        "queens-compsa": snap("queens-compsa", COMPSA_RAW),
        "queens-rec": snap("queens-rec", REC_RAW),
    }
