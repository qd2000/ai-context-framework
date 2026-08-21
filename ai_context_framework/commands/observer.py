"""Project Observer CLI commands."""

from __future__ import annotations

import argparse
import uuid
from pathlib import Path

from ai_context_framework.constants import EXIT_RUNTIME_ERROR, EXIT_SAFETY_REFUSED, JSON_SCHEMA_VERSION
from ai_context_framework.json_contract import json_enabled, print_json, set_result_payload
from ai_context_framework.observer import (
    ObserverLockedError,
    build_observer_snapshot,
    observer_lock_health,
    observer_paths,
    observer_snapshot,
    observer_status,
    resolve_observer_project,
)
from ai_context_framework.observer_storage import (
    OBSERVER_SEMANTIC_CONFIDENCE,
    SemanticSensitiveValueError,
    SemanticSourceMismatch,
    acquire_observer_lock,
    apply_semantic_interpretation,
    read_glossary,
    read_observer_history_stream,
    release_observer_lock,
    set_glossary_term,
)


def _emit(args: argparse.Namespace, payload: dict[str, object], exit_code: int = 0) -> int:
    set_result_payload(args, payload)
    if json_enabled(args):
        print_json(payload)
    else:
        if payload.get("ok"):
            print(payload.get("message") or payload.get("observer_dir") or payload.get("command"))
        else:
            print(payload.get("message") or payload.get("error_code") or "observer command failed")
    return exit_code


def _base_payload(command: str) -> dict[str, object]:
    return {
        "schema_version": JSON_SCHEMA_VERSION,
        "ok": True,
        "command": command,
        "changed_files": [],
        "error_code": None,
        "next_actions": [],
    }


def register_observer_parser(subparsers, add_json_argument) -> None:
    """Register the Observer CLI surface without bloating the root runtime."""

    observer_parser = subparsers.add_parser(
        "observer",
        help="inspect and persist read-only project Observer state",
    )
    observer_subparsers = observer_parser.add_subparsers(dest="observer_command", required=True)
    status_parser = observer_subparsers.add_parser(
        "status",
        help="show user-level Project Observer runtime status without writing",
    )
    status_parser.add_argument("path", nargs="?", type=Path, help="context path or a directory inside a project")
    add_json_argument(status_parser)
    status_parser.set_defaults(func=observer_status_command)
    snapshot_parser = observer_subparsers.add_parser(
        "snapshot",
        help="capture a read-only project/worktree snapshot into user-level Observer state",
    )
    snapshot_parser.add_argument("path", nargs="?", type=Path, help="context path or a directory inside a project")
    snapshot_parser.add_argument("--dry-run", action="store_true", help="validate the snapshot without writing Observer runtime state")
    add_json_argument(snapshot_parser)
    snapshot_parser.set_defaults(func=observer_snapshot_command)
    interpret_parser = observer_subparsers.add_parser(
        "interpret",
        help="persist a versioned human Workstream interpretation against an exact Observer fact fingerprint",
    )
    interpret_parser.add_argument("path", nargs="?", type=Path)
    interpret_parser.add_argument("--workstream", required=True)
    interpret_parser.add_argument("--source-fingerprint", required=True)
    interpret_parser.add_argument("--human-title", required=True)
    interpret_parser.add_argument("--current-focus", required=True)
    interpret_parser.add_argument("--why-now", required=True)
    interpret_parser.add_argument("--recent-proof", action="append", default=[], required=True)
    interpret_parser.add_argument("--implication", required=True)
    interpret_parser.add_argument("--next-step", required=True)
    interpret_parser.add_argument("--confidence", choices=tuple(sorted(OBSERVER_SEMANTIC_CONFIDENCE)), required=True)
    interpret_parser.add_argument("--provenance", action="append", default=[], required=True)
    add_json_argument(interpret_parser)
    interpret_parser.set_defaults(func=observer_interpret_command)
    glossary_parser = observer_subparsers.add_parser("glossary-set", help="set one project semantic glossary term")
    glossary_parser.add_argument("path", nargs="?", type=Path)
    glossary_parser.add_argument("--term", required=True)
    glossary_parser.add_argument("--human-term", required=True)
    glossary_parser.add_argument("--explanation", required=True)
    glossary_parser.add_argument("--confidence", choices=tuple(sorted(OBSERVER_SEMANTIC_CONFIDENCE)), required=True)
    glossary_parser.add_argument("--provenance", action="append", default=[], required=True)
    add_json_argument(glossary_parser)
    glossary_parser.set_defaults(func=observer_glossary_set_command)
    glossary_show_parser = observer_subparsers.add_parser("glossary", help="show the project semantic glossary without writing")
    glossary_show_parser.add_argument("path", nargs="?", type=Path)
    add_json_argument(glossary_show_parser)
    glossary_show_parser.set_defaults(func=observer_glossary_command)
    history_parser = observer_subparsers.add_parser("history", help="read reconstructed Observer history across live and rotated shards")
    history_parser.add_argument("path", nargs="?", type=Path)
    history_parser.add_argument(
        "--stream",
        choices=("timeline", "observations", "alerts", "runs", "interpretations"),
        default="timeline",
    )
    history_parser.add_argument("--limit", type=int, default=20)
    add_json_argument(history_parser)
    history_parser.set_defaults(func=observer_history_command)


def observer_status_command(args: argparse.Namespace) -> int:
    project = resolve_observer_project(getattr(args, "path", None))
    payload = {
        **_base_payload("observer status"),
        **observer_status(project),
    }
    return _emit(args, payload)


def observer_snapshot_command(args: argparse.Namespace) -> int:
    project = resolve_observer_project(getattr(args, "path", None))
    paths = observer_paths(project)
    if bool(getattr(args, "dry_run", False)):
        current = build_observer_snapshot(project)
        payload = {
            **_base_payload("observer snapshot"),
            "dry_run": True,
            "project": project.to_payload(),
            "observer_dir": str(project.observer_dir),
            "planned_observer_files": [
                str(paths["current"]),
                str(paths["timeline"]),
                str(paths["observations"]),
                str(paths["alerts"]),
                str(paths["runs"]),
                str(paths["status"]),
                str(paths["history_index"]),
                str(paths["dashboard"]),
            ],
            "snapshot": current,
            "message": "Observer snapshot validated without writing runtime state.",
        }
        return _emit(args, payload)

    try:
        current, run, status = observer_snapshot(project)
    except ObserverLockedError as exc:
        payload = {
            **_base_payload("observer snapshot"),
            "ok": False,
            "error_code": "observer_locked",
            "project": project.to_payload(),
            "observer_dir": str(project.observer_dir),
            "lock_path": str(exc.path),
            "lock_owner": exc.owner,
            "lock_health": observer_lock_health(exc.owner),
            "overlap_detected": True,
            "message": "Observer output is already owned by another active Observer run.",
            "next_actions": ["Inspect `acf observer status --json` and retry after the active Observer run releases its lock."],
        }
        return _emit(args, payload, EXIT_SAFETY_REFUSED)
    except Exception as exc:
        payload = {
            **_base_payload("observer snapshot"),
            "ok": False,
            "error_code": "observer_snapshot_failed",
            "project": project.to_payload(),
            "observer_dir": str(project.observer_dir),
            "message": str(exc),
            "next_actions": ["Inspect Observer self-health and the project read-only snapshot inputs before retrying."],
        }
        return _emit(args, payload, EXIT_RUNTIME_ERROR)

    payload = {
        **_base_payload("observer snapshot"),
        "dry_run": False,
        "project": project.to_payload(),
        "observer_dir": str(project.observer_dir),
        "observer_files": [
            str(paths["current"]),
            str(paths["timeline"]),
            str(paths["observations"]),
            str(paths["alerts"]),
            str(paths["runs"]),
            str(paths["status"]),
            str(paths["history_index"]),
            str(paths["dashboard"]),
        ],
        "snapshot": current,
        "run": run,
        "self_health": status,
        "message": "Observer snapshot updated user-level runtime state without modifying project files.",
    }
    return _emit(args, payload)


def _workstream_from_snapshot(snapshot: dict[str, object], workstream_id: str) -> dict[str, object] | None:
    for row in snapshot.get("workstreams") or []:
        if isinstance(row, dict) and row.get("id") == workstream_id:
            return row
    return None


def observer_interpret_command(args: argparse.Namespace) -> int:
    project = resolve_observer_project(getattr(args, "path", None))
    run_id = f"semantic-{uuid.uuid4()}"
    try:
        lock_path, _recovered = acquire_observer_lock(project, run_id)
    except ObserverLockedError as exc:
        return _emit(
            args,
            {
                **_base_payload("observer interpret"),
                "ok": False,
                "error_code": "observer_locked",
                "lock_path": str(exc.path),
                "lock_health": observer_lock_health(exc.owner),
                "message": "Observer semantic state is already owned by another active Observer run.",
            },
            EXIT_SAFETY_REFUSED,
        )
    try:
        snapshot = build_observer_snapshot(project)
        workstream = _workstream_from_snapshot(snapshot, args.workstream)
        if workstream is None:
            return _emit(
                args,
                {
                    **_base_payload("observer interpret"),
                    "ok": False,
                    "error_code": "observer_workstream_not_found",
                    "workstream": args.workstream,
                    "message": f"Observer cannot find Workstream {args.workstream} in the current project fact set.",
                },
                EXIT_SAFETY_REFUSED,
            )
        continuations = [
            row
            for row in snapshot.get("continuations") or []
            if isinstance(row, dict) and row.get("workstream_id") == args.workstream
        ]
        try:
            interpretation, changed = apply_semantic_interpretation(
                project,
                workstream=workstream,
                continuations=continuations,
                expected_source_fingerprint=args.source_fingerprint,
                human_title=args.human_title,
                current_focus=args.current_focus,
                why_now=args.why_now,
                recent_proof=list(args.recent_proof),
                implication=args.implication,
                next_step=args.next_step,
                confidence=args.confidence,
                provenance_refs=list(args.provenance),
            )
        except SemanticSourceMismatch as exc:
            return _emit(
                args,
                {
                    **_base_payload("observer interpret"),
                    "ok": False,
                    "error_code": "observer_semantic_source_changed",
                    "workstream": args.workstream,
                    "expected_source_fingerprint": exc.expected,
                    "current_source_fingerprint": exc.current,
                    "message": "Project facts changed after the interpretation source was read; refresh Observer facts before writing semantic state.",
                },
                EXIT_SAFETY_REFUSED,
            )
        except SemanticSensitiveValueError as exc:
            return _emit(
                args,
                {
                    **_base_payload("observer interpret"),
                    "ok": False,
                    "error_code": "observer_sensitive_value_refused",
                    "workstream": args.workstream,
                    "message": str(exc),
                },
                EXIT_SAFETY_REFUSED,
            )
        payload = {
            **_base_payload("observer interpret"),
            "project": project.to_payload(),
            "workstream": args.workstream,
            "changed": changed,
            "interpretation": interpretation,
            "message": "Observer semantic interpretation updated user-level runtime state." if changed else "Observer semantic interpretation is already current.",
        }
        return _emit(args, payload)
    finally:
        release_observer_lock(lock_path, run_id)


def observer_glossary_set_command(args: argparse.Namespace) -> int:
    project = resolve_observer_project(getattr(args, "path", None))
    run_id = f"glossary-{uuid.uuid4()}"
    try:
        lock_path, _recovered = acquire_observer_lock(project, run_id)
    except ObserverLockedError as exc:
        return _emit(
            args,
            {
                **_base_payload("observer glossary-set"),
                "ok": False,
                "error_code": "observer_locked",
                "lock_path": str(exc.path),
                "message": "Observer semantic state is already owned by another active Observer run.",
            },
            EXIT_SAFETY_REFUSED,
        )
    try:
        try:
            glossary, changed = set_glossary_term(
                project,
                term=args.term,
                human_term=args.human_term,
                explanation=args.explanation,
                confidence=args.confidence,
                provenance_refs=list(args.provenance),
            )
        except SemanticSensitiveValueError as exc:
            return _emit(
                args,
                {
                    **_base_payload("observer glossary-set"),
                    "ok": False,
                    "error_code": "observer_sensitive_value_refused",
                    "term": args.term,
                    "message": str(exc),
                },
                EXIT_SAFETY_REFUSED,
            )
        return _emit(
            args,
            {
                **_base_payload("observer glossary-set"),
                "project": project.to_payload(),
                "changed": changed,
                "term": args.term,
                "glossary": glossary,
                "message": "Observer glossary updated user-level runtime state." if changed else "Observer glossary term is already current.",
            },
        )
    finally:
        release_observer_lock(lock_path, run_id)


def observer_glossary_command(args: argparse.Namespace) -> int:
    project = resolve_observer_project(getattr(args, "path", None))
    glossary = read_glossary(project)
    return _emit(
        args,
        {
            **_base_payload("observer glossary"),
            "project": project.to_payload(),
            "glossary": glossary,
            "term_count": len(glossary.get("terms") or {}),
            "message": "Observer glossary read from user-level runtime state.",
        },
    )


def observer_history_command(args: argparse.Namespace) -> int:
    project = resolve_observer_project(getattr(args, "path", None))
    limit = int(getattr(args, "limit", 20))
    if limit < 1 or limit > 1000:
        return _emit(
            args,
            {
                **_base_payload("observer history"),
                "ok": False,
                "error_code": "observer_history_limit_invalid",
                "message": "Observer history limit must be between 1 and 1000.",
            },
            EXIT_SAFETY_REFUSED,
        )
    rows = read_observer_history_stream(project, args.stream)
    selected = rows[-limit:]
    return _emit(
        args,
        {
            **_base_payload("observer history"),
            "project": project.to_payload(),
            "stream": args.stream,
            "total_count": len(rows),
            "returned_count": len(selected),
            "records": selected,
            "message": "Observer history reconstructed from live and rotated user-level runtime state.",
        },
    )
