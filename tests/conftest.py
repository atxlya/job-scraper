from pathlib import Path

import httpx
import pytest
import respx

from app.http.client import PoliteClient

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(adapter: str, name: str) -> bytes:
    """Recorded real responses (see scripts/record_fixture.py). Never hand-written."""
    matches = sorted((FIXTURES / adapter).glob(f"{name}.*"))
    if not matches:
        raise FileNotFoundError(f"no fixture {adapter}/{name}")
    return matches[0].read_bytes()


def load_json(adapter: str, name: str):
    import json  # noqa: PLC0415

    return json.loads(load_fixture(adapter, name))


@pytest.fixture
def client():
    """A PoliteClient that never sleeps. Files that define their own `client` win."""

    async def nosleep(_s):
        return None

    return PoliteClient(min_interval_s=0, sleep=nosleep)


@pytest.fixture
def mock():
    """respx with every robots.txt answering 404 (no rules)."""
    with respx.mock(assert_all_called=False) as m:
        m.get(url__regex=r"https://[^/]+/robots\.txt").mock(return_value=httpx.Response(404))
        yield m
