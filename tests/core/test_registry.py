from pathlib import Path

import pytest
from sqlalchemy import select

import app.adapters  # noqa: F401  (registers adapters)
from app.adapters.base import ADAPTERS
from app.core.db import make_engine, make_session_factory
from app.core.models import Base, Company, Source
from app.core.registry import CompanySpec, SourceSpec, load_registry, sync_registry

SHIPPED = Path(__file__).resolve().parents[2] / "config" / "sources.yaml"


@pytest.fixture
def session():
    eng = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    with make_session_factory(eng)() as s:
        yield s


def test_unknown_adapter_rejected(tmp_path):
    f = tmp_path / "s.yaml"
    f.write_text(
        "companies:\n  - slug: x\n    name: X\n    sources:\n"
        "      - key: x1\n        adapter: nope\n        config: {}\n"
    )
    with pytest.raises(ValueError, match="nope"):
        load_registry(f)


def test_sync_upserts_and_disables_removed(session):
    spec = [
        CompanySpec(
            slug="v",
            name="Visa",
            sources=[
                SourceSpec(key="v1", adapter="workday", config={"a": 1}),
                SourceSpec(key="v2", adapter="workday", config={}),
            ],
        )
    ]
    sync_registry(session, spec)
    spec[0].sources[0].config = {"a": 2}
    spec[0].sources.pop()
    sync_registry(session, spec)
    rows = {s.key: s for s in session.scalars(select(Source))}
    assert rows["v1"].config == {"a": 2} and rows["v1"].enabled
    assert rows["v2"].enabled is False
    assert len(session.scalars(select(Company)).all()) == 1


def test_shipped_registry_valid():
    specs = load_registry(SHIPPED)
    supported = [c for c in specs if c.supported]
    unsupported = [c for c in specs if not c.supported]
    assert len(supported) == 55
    assert len(unsupported) == 16 and all(c.reason for c in unsupported)
    assert all(c.sources and all(s.enabled for s in c.sources) for c in supported)
    assert all(s.adapter in ADAPTERS for c in supported for s in c.sources)
    assert len({s.key for c in specs for s in c.sources}) == sum(len(c.sources) for c in specs)
