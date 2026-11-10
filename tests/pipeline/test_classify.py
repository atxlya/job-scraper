from pathlib import Path

import pytest

from app.adapters.base import RawJob
from app.pipeline.classify import Classification, classify, load_keywords

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
    ],
)
def test_classify_titles(title, expected):
    assert classify(job(title), KW) == Classification(*expected)


def test_platform_intern_flag():
    c = classify(job("Associate – Payments", intern=True), KW)
    assert c.is_internship is True and c.is_tech is None


def test_lowercase_it_is_not_tech():
    assert classify(job("Make it happen coordinator"), KW).is_tech is None
