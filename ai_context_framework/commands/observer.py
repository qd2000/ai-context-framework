"""Project Observer CLI commands."""

from __future__ import annotations

import argparse
import json
import uuid
from pathlib import Path

from ai_context_framework.automation_contracts import automation_prompt_execution_contract
from ai_context_framework.constants import EXIT_RUNTIME_ERROR, EXIT_SAFETY_REFUSED, JSON_SCHEMA_VERSION
from ai_context_framework.json_contract import json_enabled, print_json, set_result_payload
from ai_context_framework.commands.observer_presentation import register_observer_presentation_parsers
from ai_context_framework.observer import (
    ObserverLockedError,
    build_observer_snapshot,
    observer_lock_health,
    observer_paths,
    observer_snapshot,
    observer_status,
    resolve_observer_project,
)
from ai_context_framework.observer_target_projection import (
    ObserverTargetReadError,
    hard_failstop_target_read_timeout_if_needed,
    resolve_observer_project_bounded,
)
from ai_context_framework.observer_storage import (
    OBSERVER_SEMANTIC_CONFIDENCE,
    ProjectNarrativeSourceMismatch,
    SemanticSensitiveValueError,
    SemanticSourceMismatch,
    acquire_observer_lock,
    apply_project_narrative,
    apply_semantic_interpretation,
    project_narrative_source_projection,
    project_narrative_source_fingerprint,
    project_narrative_status,
    read_glossary,
    read_observer_history_stream,
    release_observer_lock,
    set_glossary_term,
)
from ai_context_framework.observer_targets import (
    OBSERVER_EXPECTED_TARGET_REGISTRY_SCHEMA,
    OBSERVER_TARGET_REGISTRY_SCHEMA,
    OVERVIEW_DECISIONS,
    RUN_RESULTS,
    TARGET_MODES,
    ObserverTargetRegistryError,
    record_target_run_finish,
    record_target_run_start,
    read_expected_target_registry,
    read_target_registry,
    recover_expected_targets,
    register_target,
    register_expected_target,
    remove_expected_target,
    remove_target,
    set_project_overview_decision,
    target_registry_health,
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


def _target_read_error_payload(command: str, exc: ObserverTargetReadError) -> dict[str, object]:
    return {
        **_base_payload(command),
        "ok": False,
        "error_code": exc.error_code,
        "message": str(exc),
        "next_actions": [
            "Retry only after checking the project path/Git source and confirming no prior Observer target-read worker remains active."
        ],
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
        choices=("timeline", "observations", "alerts", "runs", "interpretations", "narratives"),
        default="timeline",
    )
    history_parser.add_argument("--limit", type=int, default=20)
    add_json_argument(history_parser)
    history_parser.set_defaults(func=observer_history_command)
    narrative_source_parser = observer_subparsers.add_parser(
        "narrative-source",
        help="read the exact Project Narrative source projection and fingerprint without writing",
    )
    narrative_source_parser.add_argument("path", nargs="?", type=Path)
    narrative_source_parser.add_argument("--source-path", action="append", default=[], required=True)
    add_json_argument(narrative_source_parser)
    narrative_source_parser.set_defaults(func=observer_narrative_source_command)
    narrative_apply_parser = observer_subparsers.add_parser(
        "narrative-apply",
        help="persist a versioned Project Narrative against an exact project authority fingerprint",
    )
    narrative_apply_parser.add_argument("path", nargs="?", type=Path)
    narrative_apply_parser.add_argument("--source-fingerprint", required=True)
    narrative_apply_parser.add_argument("--source-path", action="append", default=[], required=True)
    narrative_apply_parser.add_argument("--input", type=Path, required=True, help="JSON file containing the derived Project Narrative payload")
    add_json_argument(narrative_apply_parser)
    narrative_apply_parser.set_defaults(func=observer_narrative_apply_command)
    narrative_show_parser = observer_subparsers.add_parser(
        "narrative",
        help="show current Project Narrative status against fresh project authority without writing",
    )
    narrative_show_parser.add_argument("path", nargs="?", type=Path)
    add_json_argument(narrative_show_parser)
    narrative_show_parser.set_defaults(func=observer_narrative_command)
    targets_parser = observer_subparsers.add_parser(
        "targets",
        help="show explicit Observer V2 scheduled-automation targets and their target-local projection without writing",
    )
    targets_parser.add_argument("path", nargs="?", type=Path)
    add_json_argument(targets_parser)
    targets_parser.set_defaults(func=observer_targets_command)
    target_set_parser = observer_subparsers.add_parser(
        "target-set",
        help="register or update one explicit user-level Observer scheduled-automation target",
    )
    target_set_parser.add_argument("path", nargs="?", type=Path)
    target_set_parser.add_argument("--target-id", required=True)
    target_set_parser.add_argument("--mode", choices=tuple(sorted(TARGET_MODES)), required=True)
    target_set_parser.add_argument("--title", required=True)
    target_set_parser.add_argument("--automation-ref", required=True)
    target_set_parser.add_argument("--workstream")
    target_set_parser.add_argument("--continuation-task-id")
    target_set_parser.add_argument("--route-ref")
    add_json_argument(target_set_parser)
    target_set_parser.set_defaults(func=observer_target_set_command)
    expected_target_set_parser = observer_subparsers.add_parser(
        "expected-target-set",
        help="configure one explicit expected Observer target for runtime-state recovery",
    )
    expected_target_set_parser.add_argument("path", nargs="?", type=Path)
    expected_target_set_parser.add_argument("--target-id", required=True)
    expected_target_set_parser.add_argument("--mode", choices=tuple(sorted(TARGET_MODES)), required=True)
    expected_target_set_parser.add_argument("--title", required=True)
    expected_target_set_parser.add_argument("--automation-ref", required=True)
    expected_target_set_parser.add_argument("--workstream")
    expected_target_set_parser.add_argument("--continuation-task-id")
    expected_target_set_parser.add_argument("--route-ref")
    add_json_argument(expected_target_set_parser)
    expected_target_set_parser.set_defaults(func=observer_expected_target_set_command)
    target_remove_parser = observer_subparsers.add_parser(
        "target-remove",
        help="remove one explicit user-level Observer scheduled-automation target",
    )
    target_remove_parser.add_argument("path", nargs="?", type=Path)
    target_remove_parser.add_argument("--target-id", required=True)
    add_json_argument(target_remove_parser)
    target_remove_parser.set_defaults(func=observer_target_remove_command)
    expected_target_remove_parser = observer_subparsers.add_parser(
        "expected-target-remove",
        help="remove one explicit expected Observer target recovery configuration",
    )
    expected_target_remove_parser.add_argument("path", nargs="?", type=Path)
    expected_target_remove_parser.add_argument("--target-id", required=True)
    add_json_argument(expected_target_remove_parser)
    expected_target_remove_parser.set_defaults(func=observer_expected_target_remove_command)
    target_recover_parser = observer_subparsers.add_parser(
        "target-recover",
        help="idempotently restore missing registered targets from explicit expected-target configuration",
    )
    target_recover_parser.add_argument("path", nargs="?", type=Path)
    add_json_argument(target_recover_parser)
    target_recover_parser.set_defaults(func=observer_target_recover_command)
    overview_parser = observer_subparsers.add_parser(
        "project-overview-set",
        help="record the evidence-backed conditional Project Overview decision in user-level Observer state",
    )
    overview_parser.add_argument("path", nargs="?", type=Path)
    overview_parser.add_argument("--decision", choices=tuple(sorted(OVERVIEW_DECISIONS)), required=True)
    overview_parser.add_argument("--reason")
    overview_parser.add_argument("--evidence-ref", action="append", default=[])
    overview_parser.add_argument("--authority-fingerprint")
    add_json_argument(overview_parser)
    overview_parser.set_defaults(func=observer_project_overview_set_command)
    run_start_parser = observer_subparsers.add_parser(
        "target-run-start",
        help="record a narrow user-level scheduled-activation start marker when no continuation round is available",
    )
    run_start_parser.add_argument("path", nargs="?", type=Path)
    run_start_parser.add_argument("--target-id", required=True)
    run_start_parser.add_argument("--run-id", required=True)
    run_start_parser.add_argument("--route-ref")
    run_start_parser.add_argument("--evidence-ref", action="append", default=[])
    add_json_argument(run_start_parser)
    run_start_parser.set_defaults(func=observer_target_run_start_command)
    run_finish_parser = observer_subparsers.add_parser(
        "target-run-finish",
        help="record a narrow user-level scheduled-activation finish marker without fabricating missing end times",
    )
    run_finish_parser.add_argument("path", nargs="?", type=Path)
    run_finish_parser.add_argument("--target-id", required=True)
    run_finish_parser.add_argument("--run-id", required=True)
    run_finish_parser.add_argument("--result", choices=tuple(sorted(RUN_RESULTS)), required=True)
    run_finish_parser.add_argument("--major-outcome")
    run_finish_parser.add_argument("--route-ref")
    run_finish_parser.add_argument("--evidence-ref", action="append", default=[])
    add_json_argument(run_finish_parser)
    run_finish_parser.set_defaults(func=observer_target_run_finish_command)
    register_observer_presentation_parsers(observer_subparsers, add_json_argument)


def observer_status_command(args: argparse.Namespace) -> int:
    project = resolve_observer_project(getattr(args, "path", None))
    payload = {
        **_base_payload("observer status"),
        **observer_status(project),
        "automation_prompt_execution_contract": automation_prompt_execution_contract(),
    }
    return _emit(args, payload)


def _target_registry_error_payload(command: str, exc: ObserverTargetRegistryError) -> dict[str, object]:
    return {
        **_base_payload(command),
        "ok": False,
        "error_code": "observer_target_registry_invalid",
        "message": str(exc),
        "next_actions": [
            "Inspect the explicit user-level Observer Target Registry and correct the invalid target/decision; do not infer display targets from Workstream/worktree existence."
        ],
    }


def _target_sensitive_value_payload(command: str, exc: SemanticSensitiveValueError) -> dict[str, object]:
    return {
        **_base_payload(command),
        "ok": False,
        "error_code": "observer_sensitive_value_refused",
        "message": str(exc),
        "next_actions": [
            "Remove credential-like material from Observer target metadata/evidence and retry with a secret-safe reference."
        ],
    }


def _target_registry_locked_payload(command: str, exc: ObserverLockedError) -> dict[str, object]:
    return {
        **_base_payload(command),
        "ok": False,
        "error_code": "observer_locked",
        "lock_path": str(exc.path),
        "lock_health": observer_lock_health(exc.owner),
        "message": "Observer user-level state is already owned by another active Observer run.",
        "next_actions": ["Inspect `acf observer status --json` and retry after the active Observer run releases its lock."],
    }


def observer_targets_command(args: argparse.Namespace) -> int:
    project = resolve_observer_project(getattr(args, "path", None))
    try:
        registry = read_target_registry(project)
        expected_registry = read_expected_target_registry(project)
        snapshot = build_observer_snapshot(project)
    except SemanticSensitiveValueError as exc:
        return _emit(args, _target_sensitive_value_payload("observer targets", exc), EXIT_SAFETY_REFUSED)
    except ObserverTargetRegistryError as exc:
        return _emit(args, _target_registry_error_payload("observer targets", exc), EXIT_SAFETY_REFUSED)
    targets = snapshot.get("targets") if isinstance(snapshot.get("targets"), dict) else {}
    return _emit(
        args,
        {
            **_base_payload("observer targets"),
            "project": project.to_payload(),
            "registry_schema": OBSERVER_TARGET_REGISTRY_SCHEMA,
            "registry": registry,
            "expected_registry_schema": OBSERVER_EXPECTED_TARGET_REGISTRY_SCHEMA,
            "expected_registry": expected_registry,
            "registry_health": target_registry_health(
                project,
                registry=registry,
                expected_registry=expected_registry,
            ),
            "target_views": targets,
            "message": "Explicit Observer scheduled-automation targets read without writing runtime state.",
        },
    )


def observer_target_set_command(args: argparse.Namespace) -> int:
    try:
        project = resolve_observer_project_bounded(getattr(args, "path", None))
    except ObserverTargetReadError as exc:
        exit_code = _emit(args, _target_read_error_payload("observer target-set", exc), EXIT_RUNTIME_ERROR)
        hard_failstop_target_read_timeout_if_needed(exc, exit_code)
        return exit_code
    run_id = f"target-registry-{uuid.uuid4()}"
    try:
        lock_path, _recovered = acquire_observer_lock(project, run_id)
    except ObserverLockedError as exc:
        return _emit(args, _target_registry_locked_payload("observer target-set", exc), EXIT_SAFETY_REFUSED)
    try:
        try:
            registry, changed = register_target(
                project,
                target_id=args.target_id,
                mode=args.mode,
                title=args.title,
                automation_ref=args.automation_ref,
                workstream_id=args.workstream,
                continuation_task_id=args.continuation_task_id,
                route_ref=args.route_ref,
            )
        except SemanticSensitiveValueError as exc:
            return _emit(
                args,
                _target_sensitive_value_payload("observer target-set", exc),
                EXIT_SAFETY_REFUSED,
            )
        except ObserverTargetRegistryError as exc:
            return _emit(args, _target_registry_error_payload("observer target-set", exc), EXIT_SAFETY_REFUSED)
        return _emit(
            args,
            {
                **_base_payload("observer target-set"),
                "project": project.to_payload(),
                "target_id": args.target_id,
                "changed": changed,
                "registry": registry,
                "message": "Observer target registry updated." if changed else "Observer target is already current.",
            },
        )
    finally:
        release_observer_lock(lock_path, run_id)


def observer_expected_target_set_command(args: argparse.Namespace) -> int:
    try:
        project = resolve_observer_project_bounded(getattr(args, "path", None))
    except ObserverTargetReadError as exc:
        exit_code = _emit(args, _target_read_error_payload("observer expected-target-set", exc), EXIT_RUNTIME_ERROR)
        hard_failstop_target_read_timeout_if_needed(exc, exit_code)
        return exit_code
    run_id = f"expected-target-registry-{uuid.uuid4()}"
    try:
        lock_path, _recovered = acquire_observer_lock(project, run_id)
    except ObserverLockedError as exc:
        return _emit(args, _target_registry_locked_payload("observer expected-target-set", exc), EXIT_SAFETY_REFUSED)
    try:
        try:
            registry, changed = register_expected_target(
                project,
                target_id=args.target_id,
                mode=args.mode,
                title=args.title,
                automation_ref=args.automation_ref,
                workstream_id=args.workstream,
                continuation_task_id=args.continuation_task_id,
                route_ref=args.route_ref,
            )
        except SemanticSensitiveValueError as exc:
            return _emit(args, _target_sensitive_value_payload("observer expected-target-set", exc), EXIT_SAFETY_REFUSED)
        except ObserverTargetRegistryError as exc:
            return _emit(args, _target_registry_error_payload("observer expected-target-set", exc), EXIT_SAFETY_REFUSED)
        return _emit(
            args,
            {
                **_base_payload("observer expected-target-set"),
                "project": project.to_payload(),
                "target_id": args.target_id,
                "changed": changed,
                "expected_registry": registry,
                "message": "Observer expected-target recovery configuration updated." if changed else "Observer expected target is already current.",
            },
        )
    finally:
        release_observer_lock(lock_path, run_id)


def observer_target_remove_command(args: argparse.Namespace) -> int:
    project = resolve_observer_project(getattr(args, "path", None))
    run_id = f"target-registry-{uuid.uuid4()}"
    try:
        lock_path, _recovered = acquire_observer_lock(project, run_id)
    except ObserverLockedError as exc:
        return _emit(args, _target_registry_locked_payload("observer target-remove", exc), EXIT_SAFETY_REFUSED)
    try:
        try:
            registry, changed = remove_target(project, args.target_id)
        except SemanticSensitiveValueError as exc:
            return _emit(
                args,
                _target_sensitive_value_payload("observer target-remove", exc),
                EXIT_SAFETY_REFUSED,
            )
        except ObserverTargetRegistryError as exc:
            return _emit(args, _target_registry_error_payload("observer target-remove", exc), EXIT_SAFETY_REFUSED)
        return _emit(
            args,
            {
                **_base_payload("observer target-remove"),
                "project": project.to_payload(),
                "target_id": args.target_id,
                "changed": changed,
                "registry": registry,
                "message": "Observer target removed." if changed else "Observer target was not registered.",
            },
        )
    finally:
        release_observer_lock(lock_path, run_id)


def observer_expected_target_remove_command(args: argparse.Namespace) -> int:
    project = resolve_observer_project(getattr(args, "path", None))
    run_id = f"expected-target-registry-{uuid.uuid4()}"
    try:
        lock_path, _recovered = acquire_observer_lock(project, run_id)
    except ObserverLockedError as exc:
        return _emit(args, _target_registry_locked_payload("observer expected-target-remove", exc), EXIT_SAFETY_REFUSED)
    try:
        try:
            registry, changed = remove_expected_target(project, args.target_id)
            target_registry = read_target_registry(project)
            health = target_registry_health(
                project,
                registry=target_registry,
                expected_registry=registry,
            )
        except ObserverTargetRegistryError as exc:
            return _emit(args, _target_registry_error_payload("observer expected-target-remove", exc), EXIT_SAFETY_REFUSED)
        if args.target_id in health.get("withdrawn_registered_target_ids", []):
            message = (
                "Observer expected-target withdrawal recorded, but the target remains registered; "
                "remove the live target explicitly before considering the withdrawal complete."
            )
        else:
            message = "Observer expected target removed." if changed else "Observer expected target was not configured."
        return _emit(
            args,
            {
                **_base_payload("observer expected-target-remove"),
                "project": project.to_payload(),
                "target_id": args.target_id,
                "changed": changed,
                "expected_registry": registry,
                "registry_health": health,
                "message": message,
            },
        )
    finally:
        release_observer_lock(lock_path, run_id)


def observer_target_recover_command(args: argparse.Namespace) -> int:
    try:
        project = resolve_observer_project_bounded(getattr(args, "path", None))
    except ObserverTargetReadError as exc:
        exit_code = _emit(args, _target_read_error_payload("observer target-recover", exc), EXIT_RUNTIME_ERROR)
        hard_failstop_target_read_timeout_if_needed(exc, exit_code)
        return exit_code
    run_id = f"target-registry-recovery-{uuid.uuid4()}"
    try:
        lock_path, _recovered = acquire_observer_lock(project, run_id)
    except ObserverLockedError as exc:
        return _emit(args, _target_registry_locked_payload("observer target-recover", exc), EXIT_SAFETY_REFUSED)
    try:
        try:
            registry, recovered_target_ids, changed = recover_expected_targets(project)
            expected_registry = read_expected_target_registry(project)
            health = target_registry_health(
                project,
                registry=registry,
                expected_registry=expected_registry,
            )
        except ObserverTargetRegistryError as exc:
            return _emit(args, _target_registry_error_payload("observer target-recover", exc), EXIT_SAFETY_REFUSED)
        health_status = str(health.get("status") or "")
        if health_status == "conflict":
            message = (
                "Observer target registry conflicts with explicit expected-target configuration; "
                "recovery did not overwrite existing target bindings."
            )
        elif changed:
            message = "Observer expected targets recovered."
        elif health_status == "unconfigured":
            message = "Observer expected-target recovery contract is not configured."
        elif health_status == "configured_empty":
            message = "Observer expected-target contract is explicitly empty; no targets were recovered."
        else:
            message = "Observer target registry already matches explicit expected targets."
        return _emit(
            args,
            {
                **_base_payload("observer target-recover"),
                "project": project.to_payload(),
                "changed": changed,
                "recovered_target_ids": recovered_target_ids,
                "registry": registry,
                "expected_registry": expected_registry,
                "registry_health": health,
                "message": message,
            },
        )
    finally:
        release_observer_lock(lock_path, run_id)


def observer_project_overview_set_command(args: argparse.Namespace) -> int:
    project = resolve_observer_project(getattr(args, "path", None))
    run_id = f"target-registry-{uuid.uuid4()}"
    try:
        lock_path, _recovered = acquire_observer_lock(project, run_id)
    except ObserverLockedError as exc:
        return _emit(args, _target_registry_locked_payload("observer project-overview-set", exc), EXIT_SAFETY_REFUSED)
    try:
        try:
            registry, changed = set_project_overview_decision(
                project,
                decision=args.decision,
                reason=args.reason,
                evidence_refs=list(args.evidence_ref),
                authority_fingerprint=args.authority_fingerprint,
            )
        except SemanticSensitiveValueError as exc:
            return _emit(
                args,
                _target_sensitive_value_payload("observer project-overview-set", exc),
                EXIT_SAFETY_REFUSED,
            )
        except ObserverTargetRegistryError as exc:
            return _emit(
                args,
                _target_registry_error_payload("observer project-overview-set", exc),
                EXIT_SAFETY_REFUSED,
            )
        return _emit(
            args,
            {
                **_base_payload("observer project-overview-set"),
                "project": project.to_payload(),
                "changed": changed,
                "project_overview": registry.get("project_overview"),
                "registry": registry,
                "message": "Project Overview decision updated." if changed else "Project Overview decision is already current.",
            },
        )
    finally:
        release_observer_lock(lock_path, run_id)


def observer_target_run_start_command(args: argparse.Namespace) -> int:
    project = resolve_observer_project(getattr(args, "path", None))
    lock_owner = f"target-run-{uuid.uuid4()}"
    try:
        lock_path, _recovered = acquire_observer_lock(project, lock_owner)
    except ObserverLockedError as exc:
        return _emit(args, _target_registry_locked_payload("observer target-run-start", exc), EXIT_SAFETY_REFUSED)
    try:
        try:
            event, changed = record_target_run_start(
                project,
                target_id=args.target_id,
                run_id=args.run_id,
                route_ref=args.route_ref,
                evidence_refs=list(args.evidence_ref),
            )
        except SemanticSensitiveValueError as exc:
            return _emit(
                args,
                _target_sensitive_value_payload("observer target-run-start", exc),
                EXIT_SAFETY_REFUSED,
            )
        except ObserverTargetRegistryError as exc:
            return _emit(
                args,
                _target_registry_error_payload("observer target-run-start", exc),
                EXIT_SAFETY_REFUSED,
            )
        return _emit(
            args,
            {
                **_base_payload("observer target-run-start"),
                "project": project.to_payload(),
                "target_id": args.target_id,
                "run_id": args.run_id,
                "changed": changed,
                "event": event,
                "message": "Target run start marker recorded." if changed else "Target run start marker is already current.",
            },
        )
    finally:
        release_observer_lock(lock_path, lock_owner)


def observer_target_run_finish_command(args: argparse.Namespace) -> int:
    project = resolve_observer_project(getattr(args, "path", None))
    lock_owner = f"target-run-{uuid.uuid4()}"
    try:
        lock_path, _recovered = acquire_observer_lock(project, lock_owner)
    except ObserverLockedError as exc:
        return _emit(args, _target_registry_locked_payload("observer target-run-finish", exc), EXIT_SAFETY_REFUSED)
    try:
        try:
            event, changed = record_target_run_finish(
                project,
                target_id=args.target_id,
                run_id=args.run_id,
                result=args.result,
                major_outcome=args.major_outcome,
                route_ref=args.route_ref,
                evidence_refs=list(args.evidence_ref),
            )
        except SemanticSensitiveValueError as exc:
            return _emit(
                args,
                _target_sensitive_value_payload("observer target-run-finish", exc),
                EXIT_SAFETY_REFUSED,
            )
        except ObserverTargetRegistryError as exc:
            return _emit(
                args,
                _target_registry_error_payload("observer target-run-finish", exc),
                EXIT_SAFETY_REFUSED,
            )
        return _emit(
            args,
            {
                **_base_payload("observer target-run-finish"),
                "project": project.to_payload(),
                "target_id": args.target_id,
                "run_id": args.run_id,
                "changed": changed,
                "event": event,
                "message": "Target run finish marker recorded." if changed else "Target run finish marker is already current.",
            },
        )
    finally:
        release_observer_lock(lock_path, lock_owner)


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


def _snapshot_project_facts(snapshot: dict[str, object]) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    workstreams = [row for row in snapshot.get("workstreams") or [] if isinstance(row, dict)]
    continuations = [row for row in snapshot.get("continuations") or [] if isinstance(row, dict)]
    return workstreams, continuations


def observer_narrative_source_command(args: argparse.Namespace) -> int:
    project = resolve_observer_project(getattr(args, "path", None))
    snapshot = build_observer_snapshot(project)
    workstreams, continuations = _snapshot_project_facts(snapshot)
    try:
        projection = project_narrative_source_projection(
            project,
            workstreams,
            continuations,
            list(args.source_path),
        )
        source_fingerprint = project_narrative_source_fingerprint(
            project,
            workstreams,
            continuations,
            list(args.source_path),
        )
    except (OSError, ValueError) as exc:
        return _emit(
            args,
            {
                **_base_payload("observer narrative-source"),
                "ok": False,
                "error_code": "observer_project_narrative_source_invalid",
                "message": str(exc),
            },
            EXIT_SAFETY_REFUSED,
        )
    return _emit(
        args,
        {
            **_base_payload("observer narrative-source"),
            "project": project.to_payload(),
            "source_fingerprint": source_fingerprint,
            "source_projection": projection,
            "message": "Project Narrative source projection read from fresh project authority without writing Observer runtime state.",
        },
    )


def observer_narrative_apply_command(args: argparse.Namespace) -> int:
    project = resolve_observer_project(getattr(args, "path", None))
    input_path = Path(args.input)
    try:
        narrative_input = json.loads(input_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return _emit(
            args,
            {
                **_base_payload("observer narrative-apply"),
                "ok": False,
                "error_code": "observer_project_narrative_input_invalid",
                "message": f"cannot read Project Narrative JSON: {exc}",
            },
            EXIT_SAFETY_REFUSED,
        )
    run_id = f"project-narrative-{uuid.uuid4()}"
    try:
        lock_path, _recovered = acquire_observer_lock(project, run_id)
    except ObserverLockedError as exc:
        return _emit(
            args,
            {
                **_base_payload("observer narrative-apply"),
                "ok": False,
                "error_code": "observer_locked",
                "lock_path": str(exc.path),
                "message": "Observer Project Narrative state is already owned by another active Observer run.",
            },
            EXIT_SAFETY_REFUSED,
        )
    try:
        snapshot = build_observer_snapshot(project)
        workstreams, continuations = _snapshot_project_facts(snapshot)
        try:
            narrative, changed = apply_project_narrative(
                project,
                workstreams=workstreams,
                continuations=continuations,
                expected_source_fingerprint=args.source_fingerprint,
                source_paths=list(args.source_path),
                narrative=narrative_input,
            )
        except ProjectNarrativeSourceMismatch as exc:
            return _emit(
                args,
                {
                    **_base_payload("observer narrative-apply"),
                    "ok": False,
                    "error_code": "observer_project_narrative_source_changed",
                    "expected_source_fingerprint": exc.expected,
                    "current_source_fingerprint": exc.current,
                    "message": "Project authority changed after the Project Narrative source was read; refresh the narrative source before writing derived state.",
                },
                EXIT_SAFETY_REFUSED,
            )
        except SemanticSensitiveValueError as exc:
            return _emit(
                args,
                {
                    **_base_payload("observer narrative-apply"),
                    "ok": False,
                    "error_code": "observer_sensitive_value_refused",
                    "message": str(exc),
                },
                EXIT_SAFETY_REFUSED,
            )
        except (OSError, ValueError) as exc:
            return _emit(
                args,
                {
                    **_base_payload("observer narrative-apply"),
                    "ok": False,
                    "error_code": "observer_project_narrative_invalid",
                    "message": str(exc),
                },
                EXIT_SAFETY_REFUSED,
            )
        return _emit(
            args,
            {
                **_base_payload("observer narrative-apply"),
                "project": project.to_payload(),
                "changed": changed,
                "narrative": narrative,
                "message": "Observer Project Narrative updated user-level derived semantic state." if changed else "Observer Project Narrative is already current.",
            },
        )
    finally:
        release_observer_lock(lock_path, run_id)


def observer_narrative_command(args: argparse.Namespace) -> int:
    project = resolve_observer_project(getattr(args, "path", None))
    snapshot = build_observer_snapshot(project)
    workstreams, continuations = _snapshot_project_facts(snapshot)
    narrative = project_narrative_status(project, workstreams, continuations)
    return _emit(
        args,
        {
            **_base_payload("observer narrative"),
            "project": project.to_payload(),
            "project_narrative": narrative,
            "message": "Project Narrative status evaluated against fresh project authority without writing Observer runtime state.",
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
