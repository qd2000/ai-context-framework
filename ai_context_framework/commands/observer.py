"""Project Observer CLI commands."""

from __future__ import annotations

import argparse
from pathlib import Path

from ai_context_framework.constants import EXIT_RUNTIME_ERROR, EXIT_SAFETY_REFUSED, JSON_SCHEMA_VERSION
from ai_context_framework.json_contract import json_enabled, print_json, set_result_payload
from ai_context_framework.observer import (
    ObserverLockedError,
    build_observer_snapshot,
    observer_paths,
    observer_snapshot,
    observer_status,
    resolve_observer_project,
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
                str(paths["runs"]),
                str(paths["status"]),
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
            str(paths["runs"]),
            str(paths["status"]),
        ],
        "snapshot": current,
        "run": run,
        "self_health": status,
        "message": "Observer snapshot updated user-level runtime state without modifying project files.",
    }
    return _emit(args, payload)
