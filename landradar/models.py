from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Literal

EvidenceStatus = Literal['recorded', 'cross_checked', 'conflict']
AccessLevel = Literal['open', 'registration', 'paid', 'restricted', 'unknown']


@dataclass
class SourceRef:
    source_id: str
    name: str
    source_type: str
    url: str | None = None
    document_id: str | None = None
    locator: str | None = None
    retrieved_at: str | None = None
    effective_date: str | None = None
    access_level: AccessLevel = 'unknown'
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Fact:
    field: str
    value: Any
    source_ids: list[str]
    unit: str | None = None
    observed_at: str | None = None
    status: EvidenceStatus = 'recorded'
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ParcelRecord:
    cadastral_number: str
    sources: dict[str, SourceRef] = field(default_factory=dict)
    facts: dict[str, Fact] = field(default_factory=dict)

    def add_source(self, source: SourceRef) -> None:
        self.sources[source.source_id] = source

    def add_fact(self, fact: Fact) -> None:
        if not fact.source_ids:
            raise ValueError(f"Fact '{fact.field}' must have at least one source_id")
        missing = [sid for sid in fact.source_ids if sid not in self.sources]
        if missing:
            raise ValueError(f"Fact '{fact.field}' refers to unknown sources: {missing}")
        self.facts[fact.field] = fact

    def to_dict(self) -> dict[str, Any]:
        return {
            'cadastral_number': self.cadastral_number,
            'sources': {k: v.to_dict() for k, v in self.sources.items()},
            'facts': {k: v.to_dict() for k, v in self.facts.items()},
        }


@dataclass
class AuditResult:
    cadastral_number: str
    fact_count: int
    source_count: int
    sourced_fields: list[str]
    conflict_fields: list[str]
    missing_required_fields: list[str]
    errors: list[str]

    @property
    def is_valid(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result['is_valid'] = self.is_valid
        return result
