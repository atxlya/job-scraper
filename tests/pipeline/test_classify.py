from pathlib import Path

import pytest

from app.adapters.base import RawJob
from app.pipeline.classify import Classification, classify, degree_only, load_keywords

KW = load_keywords(Path(__file__).resolve().parents[2] / "config" / "keywords.yaml")


def job(title, **flags):
    return RawJob(external_id="1", title=title, url="u", platform_flags=flags)


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Software Engineering Intern, 2027", (True, True)),
        ("HR Intern", (True, False)),
        ("Internal Audit Manager", (False, False)),
        ("Technology Summer Analyst", (True, True)),
        ("Senior Software Engineer", (False, True)),
        ("Graduate Programme 2027", (None, None)),
        ("Research Intern – Systems", (True, True)),
        ("Student Researcher, 2027", (True, True)),
        ("International Sales Director", (False, False)),
        ("IT Support Apprentice", (True, True)),
        ("Marketing Coordinator", (False, False)),
        # Seen in the first live run: tech word plus non-tech word means "ask Gemini".
        ("Intern _Sales Operations & Data Excellence F/H", (True, None)),
        ("Substrates Materials Engineering Intern", (True, None)),
        ("Intern-Customer Experience Analytics (Health Systems Strategy)", (True, None)),
        ("Wireless Software Engineer_ Intern", (True, True)),
    ],
)
def test_classify_titles(title, expected):
    assert classify(job(title), KW) == Classification(*expected)


def test_notice_with_engg_abbreviation_is_tech():
    title = (
        "DGRE, Chandigarh invites application for Paid Internship for Engg/Science UG/PG Students"
    )
    assert classify(job(title, notice=True), KW) == Classification(True, True)


def test_platform_intern_flag():
    c = classify(job("Associate – Payments", intern=True), KW)
    assert c.is_internship is True and c.is_tech is None


def test_lowercase_it_is_not_tech():
    assert classify(job("Make it happen coordinator"), KW).is_tech is None


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Software Engineering PhD Intern, Summer 2027", "PhD"),
        ("Silicon Engineering Intern, PhD, Summer 2027", "PhD"),
        ("Research Intern (Ph.D.)", "PhD"),
        ("Doctoral Researcher Intern", "PhD"),
        ("Data Science Intern - Masters", "Master's"),
        ("Master's Student Intern, ML", "Master's"),
        ("Software Engineer Intern, MS", "Master's"),
        ("M.Tech Intern - Embedded", "Master's"),
        ("MBA Intern, Technology Strategy", "MBA"),
        # Open to Bachelor's students too: no warning.
        ("Software Engineering Intern, BS/MS, Summer 2027", None),
        ("Student Researcher, BS/MS/PhD", None),
        ("Bachelor's or Master's Intern, Data", None),
        ("Software Engineering Intern", None),
        ("Student Researcher, 2027", None),
        # "MS" counts only in capitals.
        ("Platform Intern, ms latency team", None),
    ],
)
def test_degree_only(title, expected):
    assert degree_only(title) == expected


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        (
            "DGRE, Chandigarh invites application for Paid Internship for Engg/Science UG/PG"
            " Students",
            True,
        ),
        (
            "Advt No. SAC:02:2026 dated 10.09.2026 - Inviting online applications for the posts"
            " of Junior Research Fellows, Research Associate and Project Scientist-I.",
            True,
        ),
        (
            "Recruitment for Project Staff on Various Contract positions for C-DAC, Chennai"
            " through Walk in Interview",
            True,
        ),
        ("Provisionally Selected List of JRF in DYSL-CT, Chennai", False),
        (
            "List of Shortlisted Candidates for the Final Round of Interview for Project"
            " Associate- Software Simulator Developer",
            False,
        ),
        ("CORRIGENDUM - ADVERTISEMENT REF. NO. CORP/JIT/03/2026", False),
        ("Walk-in-interview for the post of Scientific Assistant/B", False),
        (
            "Advt No.ISRO:ICRB:02(EMC-CEPO):2026 dated 28.07.2026 - Selection Panel for the post"
            " of Scientist/Engineer 'SC' (Mechanical,Computer Science)",
            False,
        ),
    ],
)
def test_notice_titles(title, expected):
    assert classify(job(title, notice=True), KW).is_internship is expected


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        # process steps, from the recorded CDAC page: still skipped
        (
            "Written Examination Result dated June 14, 2026 for the requirement of"
            " Project Engineer",
            False,
        ),
        ("C-DAC PUNE RESULT- ADVT NO. CORP_Grp. A and BGA_04_2025_PN", False),
        ("Selected candidate against JIT Adv ertisement CORP/JIT/02/2026-DL", False),
        ("Pune Centre list of selected candidates - Advertisement No : CORP/JIT/02/2026", False),
        ("CDAC TVM- SELECT LIST- JIT-11-12- PA/PT/PSS", False),
        ("Result – Project Engineer", False),
        ("Project Engineer Result", False),
        ("JRF Results", False),
        ("Result List: Project Staff", False),
        ("Provisional result JRF", False),
        ("Candidates selected for Project Associate interview", False),
        ("Merit list of JRF candidates", False),
        # openings that merely contain the words
        ("Walk-in for JRF positions in selected research projects", True),
        ("Applications invited for Interns in the Results-Based Monitoring project", True),
        ("Project Associate (results analysis) at C-DAC Pune", True),
    ],
)
def test_notice_skip_words_need_a_process_context(title, expected):
    assert classify(job(title, notice=True), KW).is_internship is expected
