from datetime import datetime

import pytest
from pydantic import ValidationError

from app.adapters.base import ADAPTERS, ListingResult, RawJob, register


def test_posted_at_must_be_aware():
    with pytest.raises(ValidationError):
        RawJob(external_id="1", title="t", url="u", posted_at=datetime(2026, 1, 1))


def test_register_adds_to_adapters():
    @register
    class Dummy:
        name = "dummy-test"

        async def list_jobs(self, client, cfg, mode):
            return ListingResult(jobs=[], reported_total=0, complete=True)

        async def fetch_detail(self, client, cfg, job):
            return job

    assert ADAPTERS["dummy-test"] is Dummy


def test_register_rejects_duplicate_name():
    @register
    class A:
        name = "dup-test"

    with pytest.raises(ValueError):

        @register
        class B:
            name = "dup-test"
