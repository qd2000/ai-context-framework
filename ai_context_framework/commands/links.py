"""Command handlers for WS003 structured link graph workflows."""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Sequence

from ai_context_framework.constants import JSON_SCHEMA_VERSION
from ai_context_framework.front_matter import parse_front_matter
from ai_context_framework.json_contract import dry_run_enabled, json_enabled, print_json, set_result_payload
from ai_context_framework.markdown import resolve_ref
from ai_context_framework.paths import require_context_root


GRAPH_FIELDS = ("promoted_to", "supersedes", "depends_on", "source", "evidence", "derived_from", "related")
BACKLINK_FIELDS = {"promoted_to", "supersedes", "depends_on"}


def knowledge_id_from_path(path: Path) -> str:
    match = re.match(r"^(K\d{3})-", path.name)
    return match.group(1) if match else path.stem


def metadata_values(metadata: dict[str, str | list[str]], field: str) -> list[str]:
    value = metadata.get(field)
    if isinstance(value, list):
        return [item for item in value if item.strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def graph_edges(root: Path) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    edges: list[dict[str, object]] = []
    broken_refs: list[dict[str, object]] = []
    knowledge_dir = root / "reference" / "knowledge"
    if not knowledge_dir.exists():
        return edges, broken_refs
    for path in sorted(knowledge_dir.glob("K*.md")):
        text = path.read_text(encoding="utf-8")
        metadata, _body, diagnostics = parse_front_matter(text)
        if diagnostics or not metadata:
            continue
        source_rel = path.relative_to(root).as_posix()
        source_id = str(metadata.get("id") or knowledge_id_from_path(path))
        title = next((line.removeprefix("#").strip() for line in text.splitlines() if line.startswith("# ")), source_id)
        for field in GRAPH_FIELDS:
            for target in metadata_values(metadata, field):
                resolved = resolve_ref(root, path, target)
                edge = {
                    "source_id": source_id,
                    "source_file": source_rel,
                    "summary": title,
                    "field": field,
                    "relation": field,
                    "target": target,
                    "resolved_path": str(resolved) if resolved else None,
                    "scope": "project" if resolved else "missing",
                }
                edges.append(edge)
                if resolved is None:
                    broken_refs.append(
                        {
                            "source_file": source_rel,
                            "field": field,
                            "target": target,
                            "severity": "error" if field in BACKLINK_FIELDS else "warning",
                        }
                    )
    return edges, broken_refs


def links_graph_payload(root: Path) -> dict[str, object]:
    edges, broken_refs = graph_edges(root)
    node_ids = sorted({str(edge["source_file"]) for edge in edges} | {str(edge["target"]) for edge in edges})
    return {
        "schema_version": JSON_SCHEMA_VERSION,
        "ok": True,
        "command": "links graph",
        "context": str(root),
        "changed_files": [],
        "nodes": [{"id": node_id} for node_id in node_ids],
        "edges": edges,
        "broken_refs": broken_refs,
        "summary": {"nodes": len(node_ids), "edges": len(edges), "broken_refs": len(broken_refs)},
        "error_code": None,
        "warnings": [],
        "next_actions": [],
    }


def emit_query(args: argparse.Namespace, payload: dict[str, object]) -> int:
    set_result_payload(args, payload)
    if json_enabled(args):
        print_json(payload)
    else:
        print(f"{payload['command']}: ok={payload['ok']}")
    return 0 if payload.get("ok") else 1


def links_graph_command(args: argparse.Namespace) -> int:
    root = require_context_root(args.path)
    return emit_query(args, links_graph_payload(root))


def links_check_command(args: argparse.Namespace) -> int:
    root = require_context_root(args.path)
    payload = links_graph_payload(root)
    broken = payload["broken_refs"]
    errors = [item for item in broken if isinstance(item, dict) and item.get("severity") == "error"]
    ok = not errors
    payload.update(
        {
            "command": "links check",
            "ok": ok,
            "error_code": None if ok else "links_broken_refs",
            "next_actions": [] if ok else ["Fix broken structured links, then rerun `acf links check`."],
        }
    )
    return emit_query(args, payload)


def links_backlinks_command(args: argparse.Namespace) -> int:
    root = require_context_root(args.path)
    edges, broken_refs = graph_edges(root)
    target = args.target.replace("\\", "/")
    backlinks = [edge for edge in edges if edge["target"] == target and edge["relation"] in BACKLINK_FIELDS]
    payload = {
        "schema_version": JSON_SCHEMA_VERSION,
        "ok": True,
        "command": "links backlinks",
        "context": str(root),
        "changed_files": [],
        "target": target,
        "backlinks": backlinks,
        "broken_refs": broken_refs,
        "error_code": None,
        "warnings": [],
        "next_actions": [],
    }
    return emit_query(args, payload)


def links_sync_backlinks_command(args: argparse.Namespace) -> int:
    root = require_context_root(args.path)
    edges, broken_refs = graph_edges(root)
    payload = {
        "schema_version": JSON_SCHEMA_VERSION,
        "ok": True,
        "command": "links sync-backlinks",
        "context": str(root),
        "dry_run": dry_run_enabled(args),
        "changed_files": [],
        "planned_edges_count": len([edge for edge in edges if edge["relation"] in BACKLINK_FIELDS]),
        "removed_edges_count": 0,
        "broken_refs": broken_refs,
        "error_code": None,
        "warnings": [],
        "next_actions": ["Rerun with `--apply` after reviewing planned backlinks."] if dry_run_enabled(args) else [],
    }
    return emit_query(args, payload)
