from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class OktmoRecodeResult:
    edges: list[tuple[str, str]]
    summary: dict[str, Any]


def recode_key(row: dict[str, str]) -> str:
    return "|".join((
        row["cancelled_code"],
        row.get("valid_code", ""),
        row["change_reference"],
    ))


def _cycle_members(edges: list[tuple[str, str]]) -> set[str]:
    adjacency: dict[str, set[str]] = {}
    for source, target in edges:
        adjacency.setdefault(source, set()).add(target)
    members: set[str] = set()
    for start in adjacency:
        stack = list(adjacency[start])
        seen: set[str] = set()
        while stack:
            node = stack.pop()
            if node == start:
                members.add(start)
                break
            if node in seen:
                continue
            seen.add(node)
            stack.extend(adjacency.get(node, ()))
    return members


def build_recode_relations(
    rows: list[dict[str, str]], subject_code: str,
) -> OktmoRecodeResult:
    selected = [
        row for row in rows
        if row["cancelled_code"].startswith(subject_code)
    ]
    exceptions: list[dict[str, str]] = []
    keys: set[str] = set()
    by_cancelled: dict[str, set[str]] = {}

    for row in selected:
        key = recode_key(row)
        if key in keys:
            exceptions.append({
                "source_row": row["_source_row_number"],
                "cancelled_code": row["cancelled_code"],
                "check": "duplicate_evidence_row",
            })
        keys.add(key)
        valid = row.get("valid_code", "")
        if valid:
            by_cancelled.setdefault(row["cancelled_code"], set()).add(valid)
            if not valid.startswith(subject_code):
                exceptions.append({
                    "source_row": row["_source_row_number"],
                    "cancelled_code": row["cancelled_code"],
                    "check": "cross_subject_replacement",
                    "valid_code": valid,
                })

    edges = [
        (row["cancelled_code"], row["valid_code"])
        for row in selected if row.get("valid_code")
    ]
    cycle_nodes = _cycle_members(edges)
    if cycle_nodes:
        for code in sorted(cycle_nodes):
            exceptions.append({
                "source_row": "",
                "cancelled_code": code,
                "check": "recode_cycle",
            })

    cancelled_codes = {source for source, _ in edges}
    chain_count = sum(1 for _, target in edges if target in cancelled_codes)
    changes = sorted({row["change_reference"] for row in selected})

    if exceptions:
        edges = []

    summary = {
        "status": "complete" if not exceptions else "invalid",
        "subject_code": subject_code,
        "selected_rows": len(selected),
        "relation_count": sum(
            1 for row in selected if row.get("valid_code")
        ) if not exceptions else 0,
        "annulled_without_replacement_count": sum(
            1 for row in selected if not row.get("valid_code")
        ),
        "change_references": changes,
        "direct_chain_link_count": chain_count,
        "multi_target_source_count": sum(
            1 for targets in by_cancelled.values() if len(targets) > 1
        ),
        "cycle_count": len(cycle_nodes),
        "exception_count": len(exceptions),
        "exception_samples": exceptions[:20],
        "inference_note": (
            "Relations are direct source assertions only; transitive "
            "replacement is not inferred."
        ),
    }
    return OktmoRecodeResult(edges=edges, summary=summary)
