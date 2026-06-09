"""Read-only upgrade assessment helpers."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Sequence

from ai_context_framework.constants import JSON_SCHEMA_VERSION
from ai_context_framework.models import CheckResult
from ai_context_framework.paths import infer_context_profile, infer_project_root, relative_display_path


STRUCTURE_REL_HINTS = (
    "active/Feedback_Inbox.md",
    "active/Task_Plan.md",
    "archive/Archive_Index.md",
    "reference/Knowledge_Index.md",
    "reference/Context_Curation_Prompt.md",
    "archive/tasks/.gitkeep",
    "archive/plans/.gitkeep",
    "archive/feedback/.gitkeep",
    "reference/knowledge/.gitkeep",
    "worklog/knowledge-drafts/.gitkeep",
    "human/Human_Index.md",
    "human/Human_Notes.md",
    "human/weekly/.gitkeep",
    "human/reports/.gitkeep",
)


def context_rel(root: Path, path: Path) -> str:
    return relative_display_path(path.resolve(), root.resolve())


def finding(
    *,
    code: str,
    severity: str,
    category: str,
    message: str,
    path: str | None = None,
    auto_fix: str = "none",
    next_actions: Sequence[str] = (),
) -> dict[str, object]:
    payload: dict[str, object] = {
        "code": code,
        "severity": severity,
        "category": category,
        "message": message,
        "auto_fix": auto_fix,
        "next_actions": list(next_actions),
    }
    if path:
        payload["path"] = path
    return payload


def structural_change(root: Path, path: Path) -> dict[str, object]:
    rel = context_rel(root, path)
    return {"path": rel, "action": "create_or_update"}


def structural_findings(root: Path, changed_files: Sequence[Path]) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    for path in changed_files:
        rel = context_rel(root, path)
        exists = path.exists()
        code = "managed_doc_update" if exists else "missing_structure"
        category = "managed_docs" if exists and rel not in STRUCTURE_REL_HINTS else "structure"
        message = f"{rel} will be refreshed by upgrade." if exists else f"{rel} is missing and can be created by upgrade."
        findings.append(
            finding(
                code=code,
                severity="info",
                category=category,
                path=rel,
                message=message,
                auto_fix="upgrade",
                next_actions=["Run `acf upgrade --check-after --json` after reviewing the plan."],
            )
        )
    return findings


def legacy_shape_findings(
    root: Path,
    profile: str,
    structural_changes: Sequence[dict[str, object]],
) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    structural_paths = {str(item.get("path") or "") for item in structural_changes}
    if profile == "minimal" and structural_changes:
        findings.append(
            finding(
                code="legacy_minimal_context",
                severity="info",
                category="structure",
                message="minimal context is missing files from the current minimal schema.",
                auto_fix="upgrade",
                next_actions=["Run `acf upgrade --check-after --json` after reviewing structural_changes."],
            )
        )
    if profile == "standard" and (
        any(path.startswith("human/") for path in structural_paths)
        or any(path in {"archive/feedback/.gitkeep", "reference/knowledge/.gitkeep", "worklog/knowledge-drafts/.gitkeep"} for path in structural_paths)
    ):
        findings.append(
            finding(
                code="old_standard_missing_layers",
                severity="info",
                category="structure",
                message="standard context is missing one or more current governance layers.",
                auto_fix="upgrade",
                next_actions=["Apply structural upgrade after reviewing which governance layer files will be created."],
            )
        )
    if profile == "standard" and not (root / "active" / "Workstreams.md").exists():
        findings.append(
            finding(
                code="workstream_not_initialized",
                severity="info",
                category="managed_docs",
                message="optional Workstream layer is not initialized; upgrade will not enable it automatically.",
                auto_fix="none",
                next_actions=["Run `acf workstream init` only if this project needs parallel Workstreams."],
            )
        )
    if (root / "active" / "Current_Task.md").exists() and "active/Current_Task.md" in structural_paths:
        text = (root / "active" / "Current_Task.md").read_text(encoding="utf-8", errors="replace")
        if "## 当前任务状态" in text and "\nActive" in text:
            findings.append(
                finding(
                    code="active_state_preserved",
                    severity="info",
                    category="managed_docs",
                    path="active/Current_Task.md",
                    message="Active Current_Task content will be preserved; upgrade only plans compatible structural notes.",
                    auto_fix="upgrade",
                    next_actions=["Review the planned Current_Task compatibility edit before applying upgrade."],
                )
            )
    if (root / "active" / "Task_Plan.md").exists() and "active/Task_Plan.md" in structural_paths:
        text = (root / "active" / "Task_Plan.md").read_text(encoding="utf-8", errors="replace")
        if "## 大任务状态" in text and "\nActive" in text:
            findings.append(
                finding(
                    code="active_state_preserved",
                    severity="info",
                    category="managed_docs",
                    path="active/Task_Plan.md",
                    message="Active Task_Plan content will be preserved; upgrade only plans compatible structural notes.",
                    auto_fix="upgrade",
                    next_actions=["Review the planned Task_Plan compatibility edit before applying upgrade."],
                )
            )
    return findings


def workstream_state_findings(root: Path) -> list[dict[str, object]]:
    index = root / "active" / "Workstreams.md"
    if not index.exists():
        return []
    text = index.read_text(encoding="utf-8", errors="replace")
    statuses: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or "---" in stripped or "ID" in stripped or "暂无" in stripped:
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) >= 2 and re.match(r"^WS\d{3}$", cells[0]):
            statuses.append(cells[1])
    if not statuses:
        return [
            finding(
                code="workstream_state_inactive",
                severity="info",
                category="state",
                path="active/Workstreams.md",
                message="Workstream index is initialized but has no concrete Workstream rows.",
                auto_fix="none",
                next_actions=["No Workstream upgrade action is required."],
            )
        ]
    findings: list[dict[str, object]] = []
    active_like = [status for status in statuses if status in {"Active", "Blocked", "ReadyToMerge", "Merging"}]
    if not active_like:
        findings.append(
            finding(
                code="workstream_state_inactive",
                severity="info",
                category="state",
                path="active/Workstreams.md",
                message="Workstream index has no active, blocked, ready, or merging Workstream.",
                auto_fix="none",
                next_actions=["No Workstream upgrade action is required."],
            )
        )
    elif len(active_like) == 1 and active_like[0] == "Active":
        findings.append(
            finding(
                code="workstream_state_active",
                severity="info",
                category="state",
                path="active/Workstreams.md",
                message="Workstream index has one active Workstream.",
                auto_fix="none",
                next_actions=["Continue using `acf workstream context <ID>` for the active Workstream."],
            )
        )
    elif len(active_like) > 1:
        findings.append(
            finding(
                code="workstream_state_parallel",
                severity="info",
                category="state",
                path="active/Workstreams.md",
                message="Workstream index has multiple active-like Workstreams.",
                auto_fix="none",
                next_actions=["Use Workstream guard/preflight to coordinate parallel write scopes."],
            )
        )
    if any(status in {"ReadyToMerge", "Merging"} for status in statuses):
        findings.append(
            finding(
                code="workstream_merge_state",
                severity="info",
                category="state",
                path="active/Workstreams.md",
                message="Workstream index contains ReadyToMerge or Merging work.",
                auto_fix="none",
                next_actions=["Review merge request and merge_resolution before marking the Workstream Done."],
            )
        )
    if any(status in {"Done", "Cancelled"} for status in statuses):
        findings.append(
            finding(
                code="workstream_terminal_retained",
                severity="info",
                category="state",
                path="active/Workstreams.md",
                message="Workstream index retains terminal Workstream rows.",
                auto_fix="archive_draft",
                next_actions=["Run `acf workstream archive-candidates --json` if terminal rows are no longer needed in active context."],
            )
        )
    return findings


def duplicate_current_fact_findings(root: Path) -> list[dict[str, object]]:
    context = root / "active" / "Context.md"
    if not context.exists():
        return []
    seen: dict[str, int] = {}
    findings: list[dict[str, object]] = []
    for line in context.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if not stripped.startswith(("- ", "* ")):
            continue
        normalized = re.sub(r"\s+", " ", stripped[2:].strip())
        if not normalized:
            continue
        seen[normalized] = seen.get(normalized, 0) + 1
        if seen[normalized] == 2:
            findings.append(
                finding(
                    code="duplicate_or_conflicting_current_fact",
                    severity="warning",
                    category="semantic",
                    path="active/Context.md",
                    message=f"duplicate current fact candidate: {normalized}",
                    auto_fix="curation_draft",
                    next_actions=["Review duplicate current facts and keep one authority wording."],
                )
            )
    return findings


def marker_findings(root: Path) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    marker_re = re.compile(r"<!--\s*(ACF:[A-Z0-9:_-]+):(START|END)\s*-->")
    for path in root.rglob("*.md"):
        rel = context_rel_path(root, path)
        text = path.read_text(encoding="utf-8", errors="replace")
        counts: dict[str, dict[str, int]] = {}
        for name, side in marker_re.findall(text):
            entry = counts.setdefault(name, {"START": 0, "END": 0})
            entry[side] += 1
        for name, sides in counts.items():
            if sides["START"] > 1 or sides["END"] > 1:
                findings.append(
                    finding(
                        code="marker_duplicate",
                        severity="blocking",
                        category="managed_docs",
                        path=rel,
                        message=f"duplicate generated marker `{name}` found.",
                        auto_fix="manual",
                        next_actions=["Keep one generated marker pair and move manual content outside it."],
                    )
                )
            elif sides["START"] != sides["END"]:
                findings.append(
                    finding(
                        code="marker_collision",
                        severity="blocking",
                        category="managed_docs",
                        path=rel,
                        message=f"unbalanced generated marker `{name}` found.",
                        auto_fix="manual",
                        next_actions=["Fix the generated marker pair before applying upgrade or sync commands."],
                    )
                )
    return findings


def covered_by_structural_change(error: str, structural_paths: set[str]) -> bool:
    for rel in structural_paths:
        if f"missing file: {rel}" == error:
            return True
        if error.startswith("missing directory: "):
            directory = error.removeprefix("missing directory: ").strip()
            if rel.startswith(directory.rstrip("/") + "/"):
                return True
    return False


def check_error_finding(error: str, structural_paths: set[str]) -> dict[str, object] | None:
    if covered_by_structural_change(error, structural_paths):
        return None
    path = error.split(":", 1)[0] if ":" in error else None
    link_target_match = re.search(r"`([^`]+)`", error)
    if link_target_match and link_target_match.group(1).replace("\\", "/") in structural_paths:
        return None
    if "contains " in error and " placeholder(s)" in error:
        return finding(
            code="template_placeholder",
            severity="warning",
            category="semantic",
            path=path,
            message=error,
            auto_fix="manual",
            next_actions=["Replace template placeholders with project-specific facts before treating the file as authoritative."],
        )
    if "broken markdown link" in error or "broken markdown reference" in error:
        return finding(
            code="broken_link",
            severity="warning",
            category="semantic",
            path=path,
            message=error,
            auto_fix="manual",
            next_actions=["Repair or remove the broken local reference after confirming the intended target."],
        )
    if "more than one subtask is Active" in error:
        return finding(
            code="multiple_active_subtasks",
            severity="warning",
            category="semantic",
            path=path,
            message=error,
            auto_fix="manual",
            next_actions=["Choose one active subtask or move parallel work into Workstreams."],
        )
    if "keep_active_until" in error and "is expired" in error:
        return finding(
            code="workstream_retention_expired",
            severity="warning",
            category="workstream",
            path=path,
            message=error,
            auto_fix="archive_draft",
            next_actions=["Run `acf workstream archive-candidates --json` and review terminal retained Workstreams."],
        )
    if "invalid keep_active_until" in error:
        return finding(
            code="workstream_invalid_keep_active_until",
            severity="blocking",
            category="workstream",
            path=path,
            message=error,
            auto_fix="manual",
            next_actions=["Use an ISO date such as `2026-06-09` or remove the retention metadata."],
        )
    if "missing merge request" in error or "missing merge target or candidate summary" in error:
        return finding(
            code="workstream_missing_merge_request",
            severity="blocking",
            category="workstream",
            path=path,
            message=error,
            auto_fix="manual",
            next_actions=["Add a Workstream merge request with target and summary before merging or marking done."],
        )
    if "ReadyToMerge workstream has unfinished stage" in error:
        return finding(
            code="workstream_unfinished_stage",
            severity="blocking",
            category="workstream",
            path=path,
            message=error,
            auto_fix="manual",
            next_actions=["Finish, skip, or cancel unfinished stages before marking the Workstream ReadyToMerge."],
        )
    if "Merging status requires type Merge or Maintenance" in error:
        return finding(
            code="workstream_invalid_merge_state",
            severity="blocking",
            category="workstream",
            path=path,
            message=error,
            auto_fix="manual",
            next_actions=["Change the Workstream type or status so Merging is only used by Merge/Maintenance workstreams."],
        )
    if "Done workstream missing evidence" in error or "Done workstream declares merge_targets but is missing merge request" in error:
        return finding(
            code="workstream_missing_evidence",
            severity="blocking",
            category="workstream",
            path=path,
            message=error,
            auto_fix="manual",
            next_actions=["Add Workstream evidence or merge request metadata before treating the Workstream as complete."],
        )
    if "Done workstream missing merge_resolution" in error:
        return finding(
            code="workstream_missing_merge_resolution",
            severity="blocking",
            category="workstream",
            path=path,
            message=error,
            auto_fix="manual",
            next_actions=["Add merge_resolution before treating the Workstream as complete."],
        )
    if "Cancelled workstream missing cancellation reason" in error:
        return finding(
            code="workstream_missing_cancellation_reason",
            severity="blocking",
            category="workstream",
            path=path,
            message=error,
            auto_fix="manual",
            next_actions=["Record the cancellation reason before keeping the Workstream as cancelled."],
        )
    if "Blocked workstream missing blocker reason" in error:
        return finding(
            code="workstream_missing_blocker_reason",
            severity="blocking",
            category="workstream",
            path=path,
            message=error,
            auto_fix="manual",
            next_actions=["Record the blocker reason before keeping the Workstream as blocked."],
        )
    if "Active workstream missing" in error:
        return finding(
            code="workstream_active_incomplete",
            severity="blocking",
            category="workstream",
            path=path,
            message=error,
            auto_fix="manual",
            next_actions=["Complete required Active Workstream metadata and sections."],
        )
    if "Done workstream stage" in error and "missing evidence" in error:
        return finding(
            code="workstream_stage_missing_evidence",
            severity="blocking",
            category="workstream",
            path=path,
            message=error,
            auto_fix="manual",
            next_actions=["Add stage evidence or change the stage status until evidence exists."],
        )
    if "Active workstream has more than one Active stage" in error:
        return finding(
            code="workstream_multiple_active_stages",
            severity="blocking",
            category="workstream",
            path=path,
            message=error,
            auto_fix="manual",
            next_actions=["Keep one Active stage or split parallel stage work into separate Workstreams."],
        )
    if "terminal workstream has Active stage" in error or "terminal workstream has non-terminal current_stage" in error:
        return finding(
            code="workstream_terminal_stage_inconsistent",
            severity="blocking",
            category="workstream",
            path=path,
            message=error,
            auto_fix="manual",
            next_actions=["Clear or finish non-terminal stage metadata on terminal Workstreams."],
        )
    if "invalid current_stage" in error or "current_stage" in error and "does not belong" in error or "current_stage" in error and "is not registered" in error or "current_stage" in error and "terminal status" in error:
        return finding(
            code="workstream_invalid_current_stage",
            severity="blocking",
            category="workstream",
            path=path,
            message=error,
            auto_fix="manual",
            next_actions=["Set current_stage to a registered, non-terminal stage owned by the Workstream, or clear it."],
        )
    if "write scope conflict" in error:
        return finding(
            code="workstream_scope_conflict",
            severity="blocking",
            category="workstream",
            path=path,
            message=error,
            auto_fix="manual",
            next_actions=["Resolve overlapping Workstream write scopes or mark the shared scope with serial coordination."],
        )
    if "invalid write_scope" in error or "front_matter_scope_invalid" in error:
        return finding(
            code="workstream_invalid_write_scope",
            severity="blocking",
            category="workstream",
            path=path,
            message=error,
            auto_fix="manual",
            next_actions=["Normalize the Workstream write_scope entry before relying on guard checks."],
        )
    if "invalid workstream stage id" in error:
        return finding(
            code="workstream_invalid_stage_id",
            severity="blocking",
            category="workstream",
            path=path,
            message=error,
            auto_fix="manual",
            next_actions=["Rename the Workstream stage id to the numeric form owned by that Workstream, for example `WS004.2`."],
        )
    if "has no valid current task status" in error:
        return finding(
            code="current_task_status_invalid",
            severity="blocking",
            category="semantic",
            path=path,
            message=error,
            auto_fix="manual",
            next_actions=["Fix active/Current_Task.md status before applying structural upgrade."],
        )
    if "generated_marker_duplicate" in error or "duplicate generated marker" in error:
        return finding(
            code="marker_duplicate",
            severity="blocking",
            category="managed_docs",
            path=path,
            message=error,
            auto_fix="manual",
            next_actions=["Keep one generated marker pair and move manual content outside it."],
        )
    if "generated_marker_unclosed" in error or "generated_marker_missing" in error or "marker collision" in error:
        return finding(
            code="marker_collision",
            severity="blocking",
            category="managed_docs",
            path=path,
            message=error,
            auto_fix="manual",
            next_actions=["Fix generated marker boundaries before applying upgrade or sync commands."],
        )
    if "duplicate current fact" in error or "conflicting current fact" in error:
        return finding(
            code="duplicate_or_conflicting_current_fact",
            severity="warning",
            category="semantic",
            path=path,
            message=error,
            auto_fix="curation_draft",
            next_actions=["Review conflicting current facts and keep the authority wording."],
        )
    if "git" in error.lower() and "dirty" in error.lower():
        return finding(
            code="git_dirty",
            severity="warning",
            category="runtime",
            path=path,
            message=error,
            auto_fix="none",
            next_actions=["Review working tree changes before applying structural upgrade."],
        )
    if "git" in error.lower() and ("unavailable" in error.lower() or "not a git" in error.lower()):
        return finding(
            code="git_unavailable",
            severity="warning",
            category="runtime",
            path=path,
            message=error,
            auto_fix="none",
            next_actions=["Continue only if non-git upgrade review is acceptable for this project."],
        )
    if "line ending" in error.lower() or "crlf" in error.lower():
        return finding(
            code="line_ending_preserved",
            severity="warning",
            category="runtime",
            path=path,
            message=error,
            auto_fix="none",
            next_actions=["Preserve existing line endings unless a formatter or explicit migration owns the change."],
        )
    if "unicode path" in error.lower() or "unicode" in error.lower():
        return finding(
            code="unicode_path_supported",
            severity="info",
            category="runtime",
            path=path,
            message=error,
            auto_fix="none",
            next_actions=["Continue using explicit paths if shell encoding is reliable."],
        )
    return finding(
        code="check_error",
        severity="warning",
        category="semantic",
        path=path,
        message=error,
        auto_fix="manual",
        next_actions=["Review the check error before applying or relying on upgraded context."],
    )


def check_warning_finding(warning: str) -> dict[str, object]:
    path = warning.split(":", 1)[0] if ":" in warning else None
    if "legacy ACF marker `ACF:UPGRADE-NOTES`" in warning:
        return finding(
            code="marker_legacy",
            severity="warning",
            category="managed_docs",
            path=path,
            message=warning,
            auto_fix="upgrade",
            next_actions=["Run structural upgrade after reviewing the plan to migrate legacy upgrade markers."],
        )
    if "terminal workstream remains active without keep_active_reason" in warning or "terminal workstream remains active without keep_active_until" in warning:
        return finding(
            code="workstream_terminal_retained",
            severity="warning",
            category="workstream",
            path=path,
            message=warning,
            auto_fix="archive_draft",
            next_actions=["Run `acf workstream archive-candidates --json` and decide whether to archive terminal Workstreams."],
        )
    return finding(
        code="check_warning",
        severity="warning",
        category="semantic",
        path=path,
        message=warning,
        auto_fix="manual",
        next_actions=["Review the warning and decide whether it should become a cleanup task."],
    )


def inventory_findings(root: Path) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    project_root = infer_project_root(root).resolve()
    root_resolved = root.resolve()
    context_rel = relative_display_path(root_resolved, project_root).replace("\\", "/")
    if context_rel != "docs/ai":
        findings.append(
            finding(
                code="nonstandard_context_path",
                severity="warning",
                category="inventory",
                path=context_rel,
                message=f"context root is `{context_rel}`; the standard project path is `docs/ai`.",
                auto_fix="manual",
                next_actions=["Keep using the explicit context path or migrate the context to `docs/ai` after reviewing links."],
            )
        )
    if root_resolved.name == "template":
        findings.append(
            finding(
                code="template_context",
                severity="warning",
                category="inventory",
                path=context_rel,
                message="target is the product template context, not a real project context.",
                auto_fix="none",
                next_actions=["Use template checks for product templates; run upgrade plans on real project contexts."],
            )
        )
    root_agents = project_root / "AGENTS.md"
    expected_link = f"{context_rel}/AGENTS.md"
    if not root_agents.exists():
        findings.append(
            finding(
                code="root_agent_missing",
                severity="warning",
                category="inventory",
                path="AGENTS.md",
                message=f"project root AGENTS.md is missing; agents may not discover `{expected_link}` naturally.",
                auto_fix="manual",
                next_actions=[f"Create a thin project-root AGENTS.md that points to `{expected_link}`."],
            )
        )
    else:
        text = root_agents.read_text(encoding="utf-8", errors="replace")
        if expected_link not in text.replace("\\", "/"):
            code = "root_agent_stale" if "AGENTS.md" in text and "/AGENTS.md" in text.replace("\\", "/") else "root_agent_custom"
            findings.append(
                finding(
                    code=code,
                    severity="warning",
                    category="inventory",
                    path="AGENTS.md",
                    message=f"project root AGENTS.md does not point to `{expected_link}`.",
                    auto_fix="manual",
                    next_actions=["Review root AGENTS.md and update it only if the custom entrypoint should delegate to this ACF context."],
                )
            )
    for draft_dir in (
        root / "worklog" / "upgrade-drafts",
        root / "worklog" / "curation-drafts",
        root / "worklog" / "archive-drafts",
    ):
        if not draft_dir.is_dir():
            continue
        for draft in sorted(draft_dir.glob("*.md")):
            findings.append(
                finding(
                    code="draft_exists",
                    severity="warning",
                    category="semantic",
                    path=context_rel_path(root, draft),
                    message=f"review draft exists: {context_rel_path(root, draft)}",
                    auto_fix="manual",
                    next_actions=["Review existing drafts before creating new cleanup drafts for this upgrade."],
                )
            )
    return findings


def context_rel_path(root: Path, path: Path) -> str:
    return relative_display_path(path.resolve(), root.resolve()).replace("\\", "/")


def upgrade_warning_finding(root: Path, warning: str) -> dict[str, object]:
    path: str | None = None
    root_text = str(root)
    if warning.startswith(root_text):
        suffix = warning[len(root_text) :].lstrip("\\/")
        path = suffix.split(":", 1)[0].replace("\\", "/")
    elif ":" in warning:
        path = warning.split(":", 1)[0]
    if "could not safely insert" in warning or "could not append plan reference prompt" in warning:
        return finding(
            code="managed_doc_upgrade_skipped",
            severity="warning",
            category="managed_docs",
            path=path,
            message=warning,
            auto_fix="manual",
            next_actions=["Review the document manually; upgrade could not safely insert the compatibility section."],
        )
    return finding(
        code="custom_managed_doc",
        severity="info",
        category="managed_docs",
        path=path,
        message=warning,
        auto_fix="upgrade",
        next_actions=["Review the marker notes that upgrade will append to the customized managed document."],
    )


def manual_actions(findings: Sequence[dict[str, object]]) -> list[dict[str, object]]:
    actions: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    for item in findings:
        if item.get("code") != "template_placeholder":
            continue
        path = str(item.get("path") or "")
        key = ("replace_placeholders", path)
        if key in seen:
            continue
        seen.add(key)
        actions.append(
            {
                "code": "replace_placeholders",
                "scope": "context",
                "path": path,
                "message": "Replace template placeholders with project facts.",
                "next_actions": [f"Review {path} and replace placeholder text with current project facts."],
            }
        )
    return actions


def readiness_for(findings: Sequence[dict[str, object]], structural_changes: Sequence[dict[str, object]]) -> str:
    if any(item.get("severity") == "blocking" for item in findings):
        return "blocked"
    noisy_categories = {"semantic", "workstream", "runtime", "inventory"}
    actionable_findings = [item for item in findings if item.get("category") != "state"]
    if any(item.get("category") in noisy_categories for item in actionable_findings):
        return "needs_cleanup"
    if structural_changes or actionable_findings:
        return "safe_to_apply_structure"
    return "current"


def recommended_commands(root: Path, readiness: str, structural_changes: Sequence[dict[str, object]]) -> list[str]:
    commands: list[str] = []
    target = quote_command_path(str(root))
    if structural_changes and readiness != "blocked":
        commands.append(f"acf upgrade {target} --check-after --json")
    commands.append(f"acf check {target} --strict --json")
    return commands


def quote_command_path(value: str) -> str:
    if re.search(r"\s", value):
        return json_string_quote(value)
    return value


def json_string_quote(value: str) -> str:
    return '"' + value.replace('"', '\\"') + '"'


def build_upgrade_plan_payload(
    root: Path,
    changed_files: Sequence[Path],
    upgrade_warnings: Sequence[str],
    check_result: CheckResult,
) -> dict[str, object]:
    profile = infer_context_profile(root)
    project_root = infer_project_root(root).resolve()
    structural_changes = [structural_change(root, path) for path in changed_files]
    structural_paths = {str(item["path"]) for item in structural_changes}
    findings = structural_findings(root, changed_files)
    findings.extend(legacy_shape_findings(root, profile, structural_changes))
    findings.extend(inventory_findings(root))
    findings.extend(workstream_state_findings(root))
    findings.extend(duplicate_current_fact_findings(root))
    findings.extend(marker_findings(root))
    findings.extend(upgrade_warning_finding(root, warning) for warning in upgrade_warnings)
    for error in check_result.errors:
        converted = check_error_finding(error, structural_paths)
        if converted is not None:
            findings.append(converted)
    findings.extend(check_warning_finding(warning) for warning in check_result.warnings)
    actions = manual_actions(findings)
    readiness = readiness_for(findings, structural_changes)
    blocking_count = sum(1 for item in findings if item.get("severity") == "blocking")
    return {
        "schema_version": JSON_SCHEMA_VERSION,
        "command": "upgrade plan",
        "ok": True,
        "error_code": None,
        "context": str(root.resolve()),
        "project_root": str(project_root),
        "profile": profile,
        "readiness": readiness,
        "changed_files": [],
        "risk_summary": {
            "structural_change_count": len(structural_changes),
            "blocking_count": blocking_count,
            "manual_count": len(actions),
            "safe_apply": readiness in {"current", "safe_to_apply_structure", "needs_cleanup"} and blocking_count == 0,
        },
        "findings": findings,
        "structural_changes": structural_changes,
        "recommended_commands": recommended_commands(root, readiness, structural_changes),
        "manual_actions": actions,
        "next_actions": upgrade_plan_next_actions(readiness, structural_changes, actions),
    }


def upgrade_plan_next_actions(
    readiness: str,
    structural_changes: Sequence[dict[str, object]],
    actions: Sequence[dict[str, object]],
) -> list[str]:
    if readiness == "current":
        return ["No upgrade actions needed."]
    next_actions = ["Review findings."]
    if structural_changes and readiness != "blocked":
        next_actions.append("Apply structural upgrade only after reviewing structural_changes.")
    if actions:
        next_actions.append("Complete manual_actions before treating the context as fully clean.")
    if readiness == "blocked":
        next_actions.append("Resolve blocking findings before running structural upgrade.")
    return next_actions
