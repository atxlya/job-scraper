"""Recorded JSON from the R4 platforms must not carry employee names, emails or phones."""

import json
import re

import pytest

from tests.conftest import FIXTURES

DIRS = ("spire2grow", "mynexthire", "ripplehire")
CONTACT_KEYS = {
    "recruiter",
    "coordinatorName",
    "coordinatorEmpName",
    "coordinatorEmpId",
    "coordinatorEmployeeMobile",
    "hiringManagerName",
    "pointOfContact",
    "primaryEmail",
    "secondaryEmail",
    "primaryPhone",
    "secondaryPhone",
}
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[a-z]{2,}", re.I)


def keys(value) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {k for v in value.values() for k in keys(v)}
    if isinstance(value, list):
        return {k for v in value for k in keys(v)}
    return set()


@pytest.mark.parametrize(
    "path",
    [p for d in DIRS for p in sorted((FIXTURES / d).glob("*.json"))],
    ids=lambda p: f"{p.parent.name}/{p.name}",
)
def test_no_contact_details(path):
    text = path.read_text(encoding="utf-8")
    assert not keys(json.loads(text)) & CONTACT_KEYS
    assert not EMAIL.findall(text)
