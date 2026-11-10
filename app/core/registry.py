"""Company and source registry: config/sources.yaml -> companies/sources tables."""

from pathlib import Path

import yaml
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.models import Company, Source


class SourceSpec(BaseModel):
    key: str
    adapter: str
    config: dict = Field(default_factory=dict)
    enabled: bool = True


class CompanySpec(BaseModel):
    slug: str
    name: str
    supported: bool = True
    reason: str | None = None
    sources: list[SourceSpec] = Field(default_factory=list)


def load_registry(path: str | Path) -> list[CompanySpec]:
    import app.adapters  # noqa: F401, PLC0415 - importing the package registers adapters
    from app.adapters.base import ADAPTERS  # noqa: PLC0415

    data = yaml.safe_load(Path(path).read_text())
    specs = [CompanySpec.model_validate(c) for c in data["companies"]]
    for c in specs:
        for s in c.sources:
            if s.adapter not in ADAPTERS:
                raise ValueError(f"{c.slug}/{s.key}: unknown adapter {s.adapter!r}")
    return specs


def sync_registry(session: Session, specs: list[CompanySpec]) -> None:
    """Upsert companies and sources. Sources missing from the YAML are disabled, not deleted,
    except ones added from the dashboard (origin "dashboard")."""
    wanted: set[str] = set()
    for spec in specs:
        company = session.scalars(select(Company).where(Company.slug == spec.slug)).first()
        if company is None:
            company = Company(slug=spec.slug, name=spec.name)
            session.add(company)
        company.name = spec.name
        company.supported = spec.supported
        company.unsupported_reason = spec.reason
        session.flush()
        for s in spec.sources:
            wanted.add(s.key)
            row = session.scalars(select(Source).where(Source.key == s.key)).first()
            if row is None:
                row = Source(key=s.key, company_id=company.id, adapter=s.adapter)
                session.add(row)
            row.company_id = company.id
            row.origin = "registry"
            row.adapter = s.adapter
            row.config = s.config
            row.enabled = s.enabled and spec.supported
    for row in session.scalars(select(Source)):
        if row.key not in wanted and row.origin != "dashboard":
            row.enabled = False
    session.flush()
