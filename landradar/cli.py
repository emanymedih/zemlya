from __future__ import annotations

import argparse

from .audit import audit_record, DEFAULT_REQUIRED_FIELDS
from .io import load_jsonl, dump_jsonl


def main() -> None:
    parser = argparse.ArgumentParser(description='Zemlya Radar — facts-only data audit')
    parser.add_argument('input', help='JSONL with sourced parcel facts')
    parser.add_argument('--output', default='audit.jsonl')
    parser.add_argument('--required', nargs='*', default=None)
    args = parser.parse_args()

    records = load_jsonl(args.input)
    required = args.required if args.required is not None else DEFAULT_REQUIRED_FIELDS
    results = [audit_record(record, required) for record in records]
    dump_jsonl([result.to_dict() for result in results], args.output)

    print(f"Records: {len(results)}")
    for result in results:
        print(
            f"{result.cadastral_number}: facts={result.fact_count} sources={result.source_count} "
            f"missing={len(result.missing_required_fields)} conflicts={len(result.conflict_fields)} "
            f"errors={len(result.errors)}"
        )


if __name__ == '__main__':
    main()
