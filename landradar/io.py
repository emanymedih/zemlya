from __future__ import annotations

import json
from pathlib import Path

from .models import ParcelRecord, SourceRef, Fact


def parcel_from_dict(data: dict) -> ParcelRecord:
    record = ParcelRecord(cadastral_number=data['cadastral_number'])
    for source_id, raw in data.get('sources', {}).items():
        payload = dict(raw)
        payload.setdefault('source_id', source_id)
        record.add_source(SourceRef(**payload))
    for field_name, raw in data.get('facts', {}).items():
        payload = dict(raw)
        payload.setdefault('field', field_name)
        record.add_fact(Fact(**payload))
    return record


def load_jsonl(path: str | Path) -> list[ParcelRecord]:
    records: list[ParcelRecord] = []
    with open(path, 'r', encoding='utf-8') as f:
        for line_number, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(parcel_from_dict(json.loads(line)))
            except Exception as exc:
                raise ValueError(f"Invalid record at line {line_number}: {exc}") from exc
    return records


def dump_jsonl(items: list[dict], path: str | Path) -> None:
    with open(path, 'w', encoding='utf-8') as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False) + '\n')
