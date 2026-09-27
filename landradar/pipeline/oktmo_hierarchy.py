from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any


def entry_key(row: dict[str, str]) -> str:
    return ":".join((
        row["oktmo_code"], row["section"],
        row["acceptance_date"], row["introduction_date"],
    ))


def level(row: dict[str, str]) -> str:
    if row["municipality_code"] == "000":
        return "subject" if row["territory_code"] == row["locality_code"] == "000" else "invalid"
    if row["locality_code"] != "000":
        return "locality" if row["section"] == "2" else "invalid"
    if row["territory_code"] != "000":
        return "settlement"
    return "municipality"


def parent_code(row: dict[str, str], child_level: str) -> str:
    subject = row["subject_code"]
    municipality = row["municipality_code"]
    if child_level == "municipality":
        return subject + "000000000"
    if child_level == "settlement":
        return subject + municipality + "000000"
    if child_level == "locality" and row["territory_code"] != "000":
        return subject + municipality + row["territory_code"] + "000"
    if child_level == "locality":
        return subject + municipality + "000000"
    raise ValueError(f"No code parent for {child_level}")


def cycle_members(edges: list[tuple[str, str]]) -> set[str]:
    parents = dict(edges)
    done: set[str] = set()
    cycles: set[str] = set()
    for start in parents:
        trail: dict[str, int] = {}
        node = start
        while node in parents and node not in done:
            if node in trail:
                cycles.update(list(trail)[trail[node]:])
                break
            trail[node] = len(trail)
            node = parents[node]
        done.update(trail)
    return cycles


@dataclass
class HierarchyResult:
    edges: list[tuple[str, str]]
    summary: dict[str, Any]


def build_hierarchy(rows: list[dict[str, str]], subject_code: str) -> HierarchyResult:
    codes: dict[str, list[dict[str, str]]] = defaultdict(list)
    levels: Counter[str] = Counter()
    keys = Counter(entry_key(row) for row in rows)
    for row in rows:
        codes[row["oktmo_code"]].append(row)
    issues: list[dict[str, str]] = []
    edges: list[tuple[str, str]] = []
    checks = {name: 0 for name in (
        "subject_membership", "level_shape", "unique_entry_key", "parent_resolution",
    )}
    children = 0
    for row in rows:
        key = entry_key(row)
        kind = level(row)
        levels[kind] += 1
        reason = {"source_row": row.get("_source_row_number", "unknown"),
                  "oktmo_code": row["oktmo_code"]}
        if row["subject_code"] != subject_code:
            issues.append({**reason, "check": "subject_membership"})
            continue
        checks["subject_membership"] += 1
        if kind == "invalid":
            issues.append({**reason, "check": "level_shape"})
            continue
        checks["level_shape"] += 1
        if keys[key] != 1:
            issues.append({**reason, "check": "duplicate_entry_key"})
            continue
        checks["unique_entry_key"] += 1
        if kind == "subject":
            checks["parent_resolution"] += 1
            continue
        children += 1
        expected_parent = parent_code(row, kind)
        candidates = [p for p in codes.get(expected_parent, []) if p["section"] == "1"]
        if len(candidates) != 1:
            issues.append({**reason, "check": "parent_resolution",
                           "parent_code": expected_parent,
                           "candidate_count": str(len(candidates))})
            continue
        parent = candidates[0]
        if level(parent) == "invalid" or parent["subject_code"] != subject_code:
            issues.append({**reason, "check": "parent_level", "parent_code": expected_parent})
            continue
        edges.append((key, entry_key(parent)))
        checks["parent_resolution"] += 1
    loops = cycle_members(edges)
    for key in sorted(loops):
        issues.append({"source_row": "unknown", "oktmo_code": key.split(":", 1)[0],
                       "check": "cycle"})
    return HierarchyResult(edges, {
        "status": "complete" if not issues else "invalid",
        "subject_code": subject_code, "total_rows": len(rows),
        "level_counts": dict(sorted(levels.items())),
        "checks_passed_rows": checks, "child_rows": children,
        "resolved_parent_relations": len(edges), "cycle_nodes": len(loops),
        "exception_count": len(issues), "exception_samples": issues[:20],
    })
