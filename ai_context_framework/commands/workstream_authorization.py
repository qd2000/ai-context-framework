"""CLI adapters for durable Workstream closeout authorization."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Mapping, Sequence

from ai_context_framework import closeout_authorization
from ai_context_framework.constants import JSON_SCHEMA_VERSION as CONTRACT_SCHEMA_VERSION
from ai_context_framework.json_contract import (
    json_enabled as contract_json_enabled,
    print_json as contract_print_json,
    set_result_payload as contract_set_result_payload,
)


def register_workstream_authorization_parsers(
    workstream_subparsers: argparse._SubParsersAction,
    *,
    validate_workstream_id,
    valid_workstream_types: Sequence[str],
    add_json_argument,
) -> None:
    """Attach the closeout-authorization CLI surface without bloating runtime.py."""

    authorization_parser = workstream_subparsers.add_parser(
        "authorization",
        help="inspect or record durable Workstream closeout authorization",
    )
    subparsers = authorization_parser.add_subparsers(
        dest="workstream_authorization_command",
        required=True,
    )

    status_parser = subparsers.add_parser(
        "status",
        help="resolve closeout authorization for one Workstream action",
    )
    status_parser.add_argument("id", type=validate_workstream_id)
    status_parser.add_argument("path", nargs="?", type=Path)
    status_parser.add_argument(
        "--action",
        required=True,
        choices=tuple(sorted(closeout_authorization.CLOSEOUT_ACTIONS)),
    )
    add_json_argument(status_parser)
    status_parser.set_defaults(func=workstream_authorization_status_command)

    list_parser = subparsers.add_parser(
        "list",
        help="list project closeout policies and explicit approval records",
    )
    list_parser.add_argument("path", nargs="?", type=Path)
    add_json_argument(list_parser)
    list_parser.set_defaults(func=workstream_authorization_list_command)

    policy_parser = subparsers.add_parser(
        "policy-set",
        help="record a durable scoped auto/manual/deny closeout policy",
    )
    policy_parser.add_argument("path", nargs="?", type=Path)
    policy_parser.add_argument(
        "--decision",
        required=True,
        choices=tuple(sorted(closeout_authorization.POLICY_DECISIONS)),
    )
    policy_parser.add_argument(
        "--action",
        action="append",
        required=True,
        choices=tuple(sorted(closeout_authorization.CLOSEOUT_ACTIONS)),
        help="authorized action; repeat for multiple actions",
    )
    policy_parser.add_argument("--workstream-id", type=validate_workstream_id)
    policy_parser.add_argument(
        "--workstream-type",
        choices=tuple(sorted(valid_workstream_types)),
    )
    policy_parser.add_argument(
        "--workstream-class",
        choices=tuple(sorted(closeout_authorization.WORKSTREAM_CLASSES)),
    )
    policy_parser.add_argument("--actor", required=True)
    policy_parser.add_argument("--authority-source", required=True)
    policy_parser.add_argument("--authority-revision")
    policy_parser.add_argument("--authority-fingerprint")
    policy_parser.add_argument("--evidence-ref", action="append", required=True)
    policy_parser.add_argument("--expires-at")
    policy_parser.add_argument("--supersedes", action="append")
    add_json_argument(policy_parser)
    policy_parser.set_defaults(func=workstream_authorization_policy_set_command)

    approve_parser = subparsers.add_parser(
        "approve",
        help="record explicit approval evidence for one Workstream/action/current authority",
    )
    approve_parser.add_argument("id", type=validate_workstream_id)
    approve_parser.add_argument("path", nargs="?", type=Path)
    approve_parser.add_argument(
        "--action",
        required=True,
        choices=tuple(sorted(closeout_authorization.CLOSEOUT_ACTIONS)),
    )
    approve_parser.add_argument("--actor", required=True)
    approve_parser.add_argument("--authority-source", required=True)
    approve_parser.add_argument("--authority-revision")
    approve_parser.add_argument("--authority-fingerprint")
    approve_parser.add_argument("--evidence-ref", action="append", required=True)
    approve_parser.add_argument("--expires-at")
    approve_parser.add_argument("--supersedes", action="append")
    add_json_argument(approve_parser)
    approve_parser.set_defaults(func=workstream_authorization_approve_command)

    revoke_parser = subparsers.add_parser(
        "revoke",
        help="revoke one closeout policy or approval record with authority evidence",
    )
    revoke_parser.add_argument("record_id")
    revoke_parser.add_argument("path", nargs="?", type=Path)
    revoke_parser.add_argument("--actor", required=True)
    revoke_parser.add_argument("--authority-source", required=True)
    revoke_parser.add_argument("--evidence-ref", action="append", required=True)
    add_json_argument(revoke_parser)
    revoke_parser.set_defaults(func=workstream_authorization_revoke_command)


def _emit_closeout_authorization_command(
    args: argparse.Namespace,
    command: str,
    payload: Mapping[str, Any],
    *,
    ok: bool = True,
    error_code: str | None = None,
    message: str | None = None,
    next_actions: Sequence[str] = (),
) -> int:
    result: dict[str, Any] = {
        "schema_version": CONTRACT_SCHEMA_VERSION,
        "command": command,
        "ok": ok,
        "error_code": error_code,
        **dict(payload),
        "next_actions": list(next_actions),
    }
    if message is not None:
        result["message"] = message
    contract_set_result_payload(args, result)
    if contract_json_enabled(args):
        contract_print_json(result)
    else:
        print(message or str(result.get("status") or command))
        for next_action in result["next_actions"]:
            print(f"next action: {next_action}")
    return 0 if ok else 2


def _closeout_authorization_error(
    args: argparse.Namespace,
    command: str,
    exc: closeout_authorization.CloseoutAuthorizationError,
) -> int:
    return _emit_closeout_authorization_command(
        args,
        command,
        {"status": "authorization_error"},
        ok=False,
        error_code=exc.code,
        message=str(exc),
        next_actions=("Fix the closeout authorization evidence/scope and retry without bypassing the resolver.",),
    )


def workstream_authorization_status_command(args: argparse.Namespace) -> int:
    command = "workstream authorization status"
    try:
        resolution = closeout_authorization.resolve_for_path(args.path, args.id, args.action)
    except closeout_authorization.CloseoutAuthorizationError as exc:
        return _closeout_authorization_error(args, command, exc)
    return _emit_closeout_authorization_command(
        args,
        command,
        {
            "status": "authorization_resolved",
            "id": args.id,
            "authorization": resolution,
        },
        next_actions=resolution.get("next_actions") or (),
    )


def workstream_authorization_list_command(args: argparse.Namespace) -> int:
    command = "workstream authorization list"
    try:
        project_root, _context_root = closeout_authorization.project_identity(args.path)
        listing = closeout_authorization.list_authorizations(project_root)
    except closeout_authorization.CloseoutAuthorizationError as exc:
        return _closeout_authorization_error(args, command, exc)
    return _emit_closeout_authorization_command(
        args,
        command,
        {
            "status": "authorizations_listed",
            "authorization_ledger": listing,
        },
    )


def workstream_authorization_policy_set_command(args: argparse.Namespace) -> int:
    command = "workstream authorization policy-set"
    try:
        project_root, _context_root = closeout_authorization.project_identity(args.path)
        written = closeout_authorization.record_policy(
            project_root,
            decision=args.decision,
            actions=args.action or (),
            actor=args.actor,
            authority_source=args.authority_source,
            authority_revision=args.authority_revision,
            authority_fingerprint=args.authority_fingerprint,
            evidence_refs=args.evidence_ref or (),
            workstream_id=args.workstream_id,
            workstream_type=args.workstream_type,
            workstream_class_name=args.workstream_class,
            expires_at=args.expires_at,
            supersedes=args.supersedes or (),
        )
    except closeout_authorization.CloseoutAuthorizationError as exc:
        return _closeout_authorization_error(args, command, exc)
    event = dict(written["event"])
    return _emit_closeout_authorization_command(
        args,
        command,
        {
            "status": "policy_recorded",
            "record_id": event["record_id"],
            "revision": event["revision"],
            "event": event,
            "ledger_path": written["ledger_path"],
        },
    )


def workstream_authorization_approve_command(args: argparse.Namespace) -> int:
    command = "workstream authorization approve"
    try:
        project_root, context_root = closeout_authorization.project_identity(args.path)
        identity = closeout_authorization.workstream_identity(
            context_root,
            args.id,
            action=args.action,
        )
        written = closeout_authorization.record_approval(
            project_root,
            workstream_id=args.id,
            workstream_type=identity["type"],
            workstream_class_name=identity["class"],
            action=args.action,
            workstream_fingerprint=identity["fingerprint"],
            actor=args.actor,
            authority_source=args.authority_source,
            authority_revision=args.authority_revision,
            authority_fingerprint=args.authority_fingerprint,
            evidence_refs=args.evidence_ref or (),
            expires_at=args.expires_at,
            supersedes=args.supersedes or (),
        )
    except closeout_authorization.CloseoutAuthorizationError as exc:
        return _closeout_authorization_error(args, command, exc)
    event = dict(written["event"])
    return _emit_closeout_authorization_command(
        args,
        command,
        {
            "status": "approval_recorded",
            "id": args.id,
            "record_id": event["record_id"],
            "revision": event["revision"],
            "workstream_fingerprint": identity["fingerprint"],
            "event": event,
            "ledger_path": written["ledger_path"],
        },
    )


def workstream_authorization_revoke_command(args: argparse.Namespace) -> int:
    command = "workstream authorization revoke"
    try:
        project_root, _context_root = closeout_authorization.project_identity(args.path)
        written = closeout_authorization.revoke_record(
            project_root,
            record_id=args.record_id,
            actor=args.actor,
            authority_source=args.authority_source,
            evidence_refs=args.evidence_ref or (),
        )
    except closeout_authorization.CloseoutAuthorizationError as exc:
        return _closeout_authorization_error(args, command, exc)
    event = dict(written["event"])
    return _emit_closeout_authorization_command(
        args,
        command,
        {
            "status": "authorization_revoked",
            "record_id": args.record_id,
            "revision": event["revision"],
            "event": event,
            "ledger_path": written["ledger_path"],
        },
    )


__all__ = [
    "register_workstream_authorization_parsers",
    "workstream_authorization_approve_command",
    "workstream_authorization_list_command",
    "workstream_authorization_policy_set_command",
    "workstream_authorization_revoke_command",
    "workstream_authorization_status_command",
]
