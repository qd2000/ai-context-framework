"""Command handler for doctor diagnostics."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ai_context_framework.constants import JSON_SCHEMA_VERSION
from ai_context_framework.json_contract import json_enabled, print_json, set_result_payload
from ai_context_framework.paths import require_context_root


@dataclass(frozen=True)
class DoctorDependencies:
    doctor_project_payload: Callable[..., Any]
    doctor_single_context_payload: Callable[..., Any]
    doctor_summary: Callable[..., Any]
    doctor_projects_next_actions: Callable[..., Any]


def doctor_command(args: argparse.Namespace, *, deps: DoctorDependencies) -> int:
    if getattr(args, "projects", None):
        if getattr(args, "fix", "none") != "none":
            raise SystemExit(
                "doctor_projects_fix_unsupported: --projects is read-only; "
                "run single-project doctor with --fix for write repairs"
            )
        if getattr(args, "report", False) or getattr(args, "draft_semantic", False):
            raise SystemExit(
                "doctor_projects_write_unsupported: --projects is read-only; "
                "run single-project doctor with --report or --draft-semantic"
            )
        project_payloads = [deps.doctor_project_payload(args, project) for project in args.projects]
        ok = all(bool(item.get("ok")) for item in project_payloads)
        findings = [
            finding
            for item in project_payloads
            for finding in item.get("findings", [])
            if isinstance(finding, dict)
        ]
        changed_files = [
            changed_file
            for item in project_payloads
            for changed_file in item.get("changed_files", [])
            if isinstance(changed_file, str)
        ]
        payload: dict[str, object] = {
            "schema_version": JSON_SCHEMA_VERSION,
            "command": "doctor",
            "ok": ok,
            "projects": project_payloads,
            "summary": deps.doctor_summary(findings),
            "changed_files": sorted(dict.fromkeys(changed_files)),
            "error_code": None if ok else "doctor_failed",
            "message": "" if ok else "one or more projects failed",
            "next_actions": deps.doctor_projects_next_actions(project_payloads, findings, getattr(args, "fix", "none"), ok),
        }
    else:
        payload = deps.doctor_single_context_payload(args, require_context_root(args.path))
    set_result_payload(args, payload)
    if json_enabled(args):
        print_json(payload)
    else:
        if "projects" in payload:
            for item in payload["projects"]:
                if isinstance(item, dict):
                    print(f"{item.get('context')}: {item.get('summary', {}).get('findings_total', 0)} finding(s)")
        else:
            print(f"doctor findings: {payload['summary']['findings_total']}")
            for finding in payload.get("findings", []):
                if isinstance(finding, dict):
                    print(f"{finding.get('severity')}: {finding.get('code')} - {finding.get('message')}")
    return 0 if payload.get("ok") else 1
