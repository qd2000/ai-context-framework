"""Observer V2 semantic-review and presentation-maintenance CLI adapters."""

from __future__ import annotations

import argparse
import json
import uuid
from pathlib import Path

from ai_context_framework.automation_contracts import (
    OBSERVER_PRESENTATION_TYPES,
    OBSERVER_SEMANTIC_REVIEW_DECISIONS,
)
from ai_context_framework.constants import EXIT_RUNTIME_ERROR, EXIT_SAFETY_REFUSED, JSON_SCHEMA_VERSION
from ai_context_framework.json_contract import json_enabled, print_json, set_result_payload
from ai_context_framework.observer import build_observer_snapshot, resolve_observer_project
from ai_context_framework.observer_presentation import (
    ObserverPresentationConcurrencyError,
    ObserverPresentationError,
    ObserverPresentationSemanticEscalationRequired,
    ObserverPresentationSourceMismatch,
    ObserverPresentationViewChanged,
    add_durable_rule,
    add_one_shot_review_request,
    apply_transient_patch,
    apply_semantic_review,
    attach_presentation_status,
    clear_transient_patch,
    presentation_status,
    withdraw_durable_rule,
)
from ai_context_framework.observer_storage import (
    ObserverLockedError,
    SemanticSensitiveValueError,
    _read_json_object,
    acquire_observer_lock,
    observer_paths,
    read_glossary,
    read_observer_history_stream,
    release_observer_lock,
    write_dashboard,
)


def _emit(args: argparse.Namespace, payload: dict[str, object], exit_code: int = 0) -> int:
    set_result_payload(args, payload)
    if json_enabled(args):
        print_json(payload)
    else:
        print(payload.get("message") or payload.get("error_code") or payload.get("command"))
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


def register_observer_presentation_parsers(observer_subparsers, add_json_argument) -> None:
    """Register the P2 user-level semantic/presentation lifecycle surface."""

    status_parser = observer_subparsers.add_parser(
        "presentation-status",
        help="show target-local semantic review and presentation-maintenance state without writing",
    )
    status_parser.add_argument("path", nargs="?", type=Path)
    add_json_argument(status_parser)
    status_parser.set_defaults(func=observer_presentation_status_command)

    request_parser = observer_subparsers.add_parser(
        "review-request-add",
        help="record one transient one-shot semantic/presentation review request for the next Production Map Review",
    )
    request_parser.add_argument("path", nargs="?", type=Path)
    request_parser.add_argument("--target-id", required=True)
    request_parser.add_argument("--request-id", required=True)
    request_parser.add_argument("--expected-target-revision", type=int, required=True)
    request_parser.add_argument("--reviewed-intent", required=True)
    request_parser.add_argument("--scope", required=True)
    request_parser.add_argument("--rationale", required=True)
    request_parser.add_argument("--evidence-ref", action="append", default=[], required=True)
    add_json_argument(request_parser)
    request_parser.set_defaults(func=observer_review_request_add_command)

    rule_parser = observer_subparsers.add_parser(
        "presentation-rule-add",
        help="record or supersede one explicit durable Observer presentation rule",
    )
    rule_parser.add_argument("path", nargs="?", type=Path)
    rule_parser.add_argument("--target-id", required=True)
    rule_parser.add_argument("--rule-id", required=True)
    rule_parser.add_argument("--expected-target-revision", type=int, required=True)
    rule_parser.add_argument("--reviewed-intent", required=True)
    rule_parser.add_argument("--scope", required=True)
    rule_parser.add_argument("--rationale", required=True)
    rule_parser.add_argument("--evidence-ref", action="append", default=[], required=True)
    rule_parser.add_argument("--supersedes")
    add_json_argument(rule_parser)
    rule_parser.set_defaults(func=observer_presentation_rule_add_command)

    withdraw_parser = observer_subparsers.add_parser(
        "presentation-rule-withdraw",
        help="withdraw one currently active durable Observer presentation rule",
    )
    withdraw_parser.add_argument("path", nargs="?", type=Path)
    withdraw_parser.add_argument("--target-id", required=True)
    withdraw_parser.add_argument("--rule-id", required=True)
    withdraw_parser.add_argument("--expected-target-revision", type=int, required=True)
    withdraw_parser.add_argument("--reason", required=True)
    withdraw_parser.add_argument("--evidence-ref", action="append", default=[], required=True)
    add_json_argument(withdraw_parser)
    withdraw_parser.set_defaults(func=observer_presentation_rule_withdraw_command)

    review_parser = observer_subparsers.add_parser(
        "semantic-review-apply",
        help="apply an auditable target-local Map Review against exact target facts and authority fingerprints",
    )
    review_parser.add_argument("path", nargs="?", type=Path)
    review_parser.add_argument("--target-id", required=True)
    review_parser.add_argument("--review-id", required=True)
    review_parser.add_argument("--expected-target-revision", type=int, required=True)
    review_parser.add_argument("--source-fingerprint", required=True)
    review_parser.add_argument("--authority-fingerprint", required=True)
    review_parser.add_argument("--authority-reread", action="store_true")
    review_parser.add_argument(
        "--decision",
        choices=tuple(OBSERVER_SEMANTIC_REVIEW_DECISIONS),
        required=True,
    )
    review_parser.add_argument("--reason", required=True)
    review_parser.add_argument("--evidence-ref", action="append", default=[], required=True)
    review_parser.add_argument("--map-relevant-signal", action="append", default=[])
    review_parser.add_argument(
        "--presentation-type",
        choices=tuple(OBSERVER_PRESENTATION_TYPES),
        required=True,
    )
    review_parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="JSON object with derived `narrative` and optional `problems`; Agent-reviewed content only",
    )
    review_parser.add_argument("--consume-one-shot", action="append", default=[])
    add_json_argument(review_parser)
    review_parser.set_defaults(func=observer_semantic_review_apply_command)

    patch_parser = observer_subparsers.add_parser(
        "transient-patch-apply",
        help="apply one immediate presentation-only target patch and deterministically rerender the canonical Dashboard",
    )
    patch_parser.add_argument("path", nargs="?", type=Path)
    patch_parser.add_argument("--target-id", required=True)
    patch_parser.add_argument("--patch-id", required=True)
    patch_parser.add_argument("--expected-target-revision", type=int, required=True)
    patch_parser.add_argument("--expected-presentation-revision", type=int, required=True)
    patch_parser.add_argument("--presentation-fingerprint", required=True)
    patch_parser.add_argument("--reviewed-intent", required=True)
    patch_parser.add_argument("--scope", required=True)
    patch_parser.add_argument("--rationale", required=True)
    patch_parser.add_argument("--evidence-ref", action="append", default=[], required=True)
    patch_parser.add_argument("--density", choices=("compact", "balanced", "detailed"), default="balanced")
    patch_parser.add_argument("--presentation-type", choices=tuple(OBSERVER_PRESENTATION_TYPES))
    patch_parser.add_argument("--emphasize-section", action="append", default=[])
    patch_parser.add_argument("--semantic-risk-signal", action="append", default=[])
    add_json_argument(patch_parser)
    patch_parser.set_defaults(func=observer_transient_patch_apply_command)

    clear_parser = observer_subparsers.add_parser(
        "transient-patch-clear",
        help="clear the active transient presentation-only patch and deterministically rerender the canonical Dashboard",
    )
    clear_parser.add_argument("path", nargs="?", type=Path)
    clear_parser.add_argument("--target-id", required=True)
    clear_parser.add_argument("--expected-target-revision", type=int, required=True)
    clear_parser.add_argument("--expected-presentation-revision", type=int, required=True)
    clear_parser.add_argument("--presentation-fingerprint", required=True)
    clear_parser.add_argument("--reason", required=True)
    clear_parser.add_argument("--evidence-ref", action="append", default=[], required=True)
    add_json_argument(clear_parser)
    clear_parser.set_defaults(func=observer_transient_patch_clear_command)


def _locked_payload(command: str, exc: ObserverLockedError) -> dict[str, object]:
    return {
        **_base_payload(command),
        "ok": False,
        "error_code": "observer_locked",
        "lock_path": str(exc.path),
        "lock_owner": exc.owner,
        "message": "Observer derived presentation state is already owned by another active Observer write.",
        "next_actions": ["Reread `acf observer presentation-status --json` after the active Observer write releases its lock."],
    }


def _concurrency_payload(command: str, exc: ObserverPresentationConcurrencyError) -> dict[str, object]:
    return {
        **_base_payload(command),
        "ok": False,
        "error_code": "observer_presentation_revision_changed",
        "expected_target_revision": exc.expected,
        "current_target_revision": exc.current,
        "message": "Observer presentation state changed after it was read; reread and re-evaluate the user intent before writing.",
        "next_actions": ["Rerun `acf observer presentation-status --json`, review current active requests/rules, and retry with the fresh target revision."],
    }


def _source_mismatch_payload(command: str, exc: ObserverPresentationSourceMismatch) -> dict[str, object]:
    return {
        **_base_payload(command),
        "ok": False,
        "error_code": "observer_target_semantic_source_changed",
        "expected_source_fingerprint": exc.expected,
        "current_source_fingerprint": exc.current,
        "message": "Target facts changed after semantic-review input was prepared; refresh target facts and authority before writing derived semantic state.",
        "next_actions": ["Rerun `acf observer presentation-status --json`, reread map-relevant authority, and generate a fresh review against the current source fingerprint."],
    }


def _presentation_view_changed_payload(command: str, exc: ObserverPresentationViewChanged) -> dict[str, object]:
    return {
        **_base_payload(command),
        "ok": False,
        "error_code": "observer_presentation_view_changed",
        "expected_presentation_revision": exc.expected_revision,
        "current_presentation_revision": exc.current_revision,
        "expected_presentation_fingerprint": exc.expected_fingerprint,
        "current_presentation_fingerprint": exc.current_fingerprint,
        "message": "Derived presentation changed after it was reviewed; reread the exact presentation revision/fingerprint before retrying.",
        "next_actions": ["Rerun `acf observer presentation-status --json`, review the current semantic state/rules/patch, and retry only after re-evaluating the requested presentation change."],
    }


def _semantic_escalation_payload(
    command: str,
    exc: ObserverPresentationSemanticEscalationRequired,
) -> dict[str, object]:
    return {
        **_base_payload(command),
        "ok": False,
        "error_code": "observer_presentation_requires_map_review",
        "semantic_risk_signals": exc.signals,
        "message": "The requested change may alter or misrepresent project semantics, so a presentation-only patch is refused.",
        "next_actions": ["Reread map-relevant authority and apply a formal `acf observer semantic-review-apply` instead of a transient presentation patch."],
    }


def _invalid_payload(command: str, exc: Exception) -> dict[str, object]:
    return {
        **_base_payload(command),
        "ok": False,
        "error_code": "observer_presentation_invalid",
        "message": str(exc),
        "next_actions": ["Reread current Observer target/presentation state and correct the reviewed intent, lifecycle metadata, authority evidence, or target identity before retrying."],
    }


def _sensitive_payload(command: str, exc: SemanticSensitiveValueError) -> dict[str, object]:
    return {
        **_base_payload(command),
        "ok": False,
        "error_code": "observer_sensitive_value_refused",
        "message": str(exc),
        "next_actions": ["Remove credential-like material and use a secret-safe evidence reference instead."],
    }


def _target_view(snapshot: dict[str, object], target_id: str) -> dict[str, object] | None:
    targets = snapshot.get("targets") if isinstance(snapshot.get("targets"), dict) else {}
    for row in targets.get("targets") or []:
        if not isinstance(row, dict):
            continue
        target = row.get("target") if isinstance(row.get("target"), dict) else {}
        if target.get("target_id") == target_id:
            return row
    return None


def observer_presentation_status_command(args: argparse.Namespace) -> int:
    project = resolve_observer_project(getattr(args, "path", None))
    try:
        snapshot = build_observer_snapshot(project)
        status = presentation_status(project, snapshot.get("targets") or {})
    except (ObserverPresentationError, SemanticSensitiveValueError) as exc:
        payload = _sensitive_payload("observer presentation-status", exc) if isinstance(exc, SemanticSensitiveValueError) else _invalid_payload("observer presentation-status", exc)
        return _emit(args, payload, EXIT_SAFETY_REFUSED)
    return _emit(
        args,
        {
            **_base_payload("observer presentation-status"),
            "project": project.to_payload(),
            "presentation": status,
            "message": "Observer target-local semantic/presentation state read without writing runtime or project files.",
        },
    )


def _run_locked_write(args: argparse.Namespace, command: str, callback) -> int:
    project = resolve_observer_project(getattr(args, "path", None))
    lock_owner = f"presentation-{uuid.uuid4()}"
    try:
        lock_path, _recovered = acquire_observer_lock(project, lock_owner)
    except ObserverLockedError as exc:
        return _emit(args, _locked_payload(command, exc), EXIT_SAFETY_REFUSED)
    try:
        try:
            payload = callback(project)
        except ObserverPresentationConcurrencyError as exc:
            return _emit(args, _concurrency_payload(command, exc), EXIT_SAFETY_REFUSED)
        except ObserverPresentationSourceMismatch as exc:
            return _emit(args, _source_mismatch_payload(command, exc), EXIT_SAFETY_REFUSED)
        except ObserverPresentationViewChanged as exc:
            return _emit(args, _presentation_view_changed_payload(command, exc), EXIT_SAFETY_REFUSED)
        except ObserverPresentationSemanticEscalationRequired as exc:
            return _emit(args, _semantic_escalation_payload(command, exc), EXIT_SAFETY_REFUSED)
        except SemanticSensitiveValueError as exc:
            return _emit(args, _sensitive_payload(command, exc), EXIT_SAFETY_REFUSED)
        except ObserverPresentationError as exc:
            return _emit(args, _invalid_payload(command, exc), EXIT_SAFETY_REFUSED)
        except (OSError, json.JSONDecodeError) as exc:
            return _emit(args, _invalid_payload(command, exc), EXIT_RUNTIME_ERROR)
        return _emit(args, payload)
    finally:
        release_observer_lock(lock_path, lock_owner)


def observer_review_request_add_command(args: argparse.Namespace) -> int:
    def write(project):
        target_state, event = add_one_shot_review_request(
            project,
            target_id=args.target_id,
            request_id=args.request_id,
            expected_target_revision=args.expected_target_revision,
            reviewed_intent=args.reviewed_intent,
            scope=args.scope,
            rationale=args.rationale,
            evidence_refs=args.evidence_ref,
        )
        return {
            **_base_payload("observer review-request-add"),
            "project": project.to_payload(),
            "target_state": target_state,
            "event": event,
            "message": "One-shot Observer semantic/presentation review request recorded in user-level derived state.",
        }

    return _run_locked_write(args, "observer review-request-add", write)


def observer_presentation_rule_add_command(args: argparse.Namespace) -> int:
    def write(project):
        target_state, event = add_durable_rule(
            project,
            target_id=args.target_id,
            rule_id=args.rule_id,
            expected_target_revision=args.expected_target_revision,
            reviewed_intent=args.reviewed_intent,
            scope=args.scope,
            rationale=args.rationale,
            evidence_refs=args.evidence_ref,
            supersedes=args.supersedes,
        )
        return {
            **_base_payload("observer presentation-rule-add"),
            "project": project.to_payload(),
            "target_state": target_state,
            "event": event,
            "message": "Durable Observer presentation rule recorded in user-level derived state.",
        }

    return _run_locked_write(args, "observer presentation-rule-add", write)


def observer_presentation_rule_withdraw_command(args: argparse.Namespace) -> int:
    def write(project):
        target_state, event = withdraw_durable_rule(
            project,
            target_id=args.target_id,
            rule_id=args.rule_id,
            expected_target_revision=args.expected_target_revision,
            reason=args.reason,
            evidence_refs=args.evidence_ref,
        )
        return {
            **_base_payload("observer presentation-rule-withdraw"),
            "project": project.to_payload(),
            "target_state": target_state,
            "event": event,
            "message": "Durable Observer presentation rule withdrawn without deleting its audit history.",
        }

    return _run_locked_write(args, "observer presentation-rule-withdraw", write)


def observer_semantic_review_apply_command(args: argparse.Namespace) -> int:
    def write(project):
        input_path = Path(args.input)
        raw = json.loads(input_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ObserverPresentationError("observer semantic-review input must be a JSON object")
        narrative = raw.get("narrative")
        if not isinstance(narrative, dict):
            raise ObserverPresentationError("observer semantic-review input requires object field `narrative`")
        problems = raw.get("problems") or []
        if not isinstance(problems, list):
            raise ObserverPresentationError("observer semantic-review input field `problems` must be a list")
        snapshot = build_observer_snapshot(project)
        target_view = _target_view(snapshot, args.target_id)
        if target_view is None:
            raise ObserverPresentationError("observer semantic-review target must be explicitly registered and present in the current target projection")
        target_state, event = apply_semantic_review(
            project,
            target_view=target_view,
            expected_target_revision=args.expected_target_revision,
            expected_source_fingerprint=args.source_fingerprint,
            review_id=args.review_id,
            authority_fingerprint=args.authority_fingerprint,
            authority_reread=args.authority_reread,
            decision=args.decision,
            reason=args.reason,
            evidence_refs=args.evidence_ref,
            map_relevant_signals=args.map_relevant_signal,
            presentation_type=args.presentation_type,
            narrative=narrative,
            problems=problems,
            consume_one_shot_request_ids=args.consume_one_shot,
        )
        return {
            **_base_payload("observer semantic-review-apply"),
            "project": project.to_payload(),
            "target_state": target_state,
            "event": event,
            "message": "Audited target semantic/Map Review state applied against exact current target facts.",
        }

    return _run_locked_write(args, "observer semantic-review-apply", write)


def _canonical_current_snapshot(project) -> dict[str, object]:
    paths = observer_paths(project)
    current = _read_json_object(paths["current"])
    if not isinstance(current, dict) or not current:
        raise ObserverPresentationError(
            "observer deterministic rerender requires an existing canonical current snapshot"
        )
    return current


def _rerender_from_current_state(
    project,
    *,
    current: dict[str, object] | None = None,
) -> dict[str, object]:
    paths = observer_paths(project)
    if current is None:
        current = _canonical_current_snapshot(project)
    status = _read_json_object(paths["status"])
    if not isinstance(status, dict):
        status = {}
    targets = current.get("targets") if isinstance(current.get("targets"), dict) else {}
    attach_presentation_status(project, targets)
    return write_dashboard(
        project,
        current=current,
        status=status,
        machine_events=read_observer_history_stream(project, "timeline"),
        interpretations=read_observer_history_stream(project, "interpretations"),
        glossary=read_glossary(project),
    )


def observer_transient_patch_apply_command(args: argparse.Namespace) -> int:
    def write(project):
        current = _canonical_current_snapshot(project)
        target_view = _target_view(current, args.target_id)
        if target_view is None:
            raise ObserverPresentationError(
                "observer transient patch target must be explicitly registered and present in the canonical current target projection"
            )
        target_state, event = apply_transient_patch(
            project,
            target_view=target_view,
            patch_id=args.patch_id,
            expected_target_revision=args.expected_target_revision,
            expected_presentation_revision=args.expected_presentation_revision,
            expected_presentation_fingerprint=args.presentation_fingerprint,
            reviewed_intent=args.reviewed_intent,
            scope=args.scope,
            rationale=args.rationale,
            evidence_refs=args.evidence_ref,
            density=args.density,
            presentation_type=args.presentation_type,
            emphasize_sections=args.emphasize_section,
            semantic_risk_signals=args.semantic_risk_signal,
        )
        dashboard = _rerender_from_current_state(project, current=current)
        return {
            **_base_payload("observer transient-patch-apply"),
            "project": project.to_payload(),
            "target_state": target_state,
            "event": event,
            "dashboard": dashboard,
            "message": "Transient presentation-only patch applied to user-level derived state and canonical Dashboard deterministically rerendered without a new Observer snapshot.",
        }

    return _run_locked_write(args, "observer transient-patch-apply", write)


def observer_transient_patch_clear_command(args: argparse.Namespace) -> int:
    def write(project):
        current = _canonical_current_snapshot(project)
        target_state, event = clear_transient_patch(
            project,
            target_id=args.target_id,
            expected_target_revision=args.expected_target_revision,
            expected_presentation_revision=args.expected_presentation_revision,
            expected_presentation_fingerprint=args.presentation_fingerprint,
            reason=args.reason,
            evidence_refs=args.evidence_ref,
        )
        dashboard = _rerender_from_current_state(project, current=current)
        return {
            **_base_payload("observer transient-patch-clear"),
            "project": project.to_payload(),
            "target_state": target_state,
            "event": event,
            "dashboard": dashboard,
            "message": "Transient presentation-only patch cleared and canonical Dashboard deterministically rerendered without changing project facts.",
        }

    return _run_locked_write(args, "observer transient-patch-clear", write)


__all__ = [
    "register_observer_presentation_parsers",
]
