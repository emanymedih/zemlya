from __future__ import annotations

from .models import ParcelRecord, AuditResult

DEFAULT_REQUIRED_FIELDS = [
    'area_sqm',
    'land_category',
    'permitted_use',
    'boundary_geometry',
    'cadastral_value_rub',
    'planning_zone',
    'pzz_document',
    'zouit',
]


def audit_record(record: ParcelRecord, required_fields: list[str] | None = None) -> AuditResult:
    required = required_fields or DEFAULT_REQUIRED_FIELDS
    errors: list[str] = []

    for name, fact in record.facts.items():
        if not fact.source_ids:
            errors.append(f"{name}: no source_id")
            continue
        for source_id in fact.source_ids:
            if source_id not in record.sources:
                errors.append(f"{name}: unknown source_id '{source_id}'")

    sourced = sorted(record.facts.keys())
    conflicts = sorted(name for name, fact in record.facts.items() if fact.status == 'conflict')
    missing = sorted(name for name in required if name not in record.facts)

    return AuditResult(
        cadastral_number=record.cadastral_number,
        fact_count=len(record.facts),
        source_count=len(record.sources),
        sourced_fields=sourced,
        conflict_fields=conflicts,
        missing_required_fields=missing,
        errors=errors,
    )
