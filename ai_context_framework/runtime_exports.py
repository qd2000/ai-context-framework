"""Explicit export contract for the ACF runtime namespace merge.

``ai_context_framework/runtime.py`` historically merged the whole ``__dict__`` of
the eight ``runtime_parts`` modules into one flat namespace and then wrote that
namespace back into every part module. The merge was order-sensitive, silent on
name collisions, and invisible to static analysis.

This module replaces the "merge everything" half of that with an explicit
allowlist:

* :data:`RUNTIME_PART_EXPORTS` lists, per part module, exactly which names may
  join the shared namespace.
* :func:`install_runtime_parts` validates that contract before merging. An
  undeclared part module, a declared name that no longer exists in the module, a
  declared name for a module that is not wired in, or a name two owners bind to
  *different* objects all fail closed at import time instead of silently
  shadowing each other.
* The second direction (shared namespace -> each part module) still injects the
  same closure as before, but derived from the explicit union in a deterministic
  order.

``scripts/runtime_export_audit.py`` recomputes the required export set from the
source and ``tests/test_runtime_contracts.py`` compares it against this table, so
the contract cannot drift silently.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence


RUNTIME_PART_EXPORTS: Mapping[str, tuple[str, ...]] = {
    "archive_workstream": (
        # Module-level __getattr__ (PEP 562) lazily forwards the public helpers of
        # commands/workstream.py (and binds their dependencies first). It is merged
        # into runtime on purpose: acf.<helper> and runtime.<helper> rely on it.
        "__getattr__",
        "append_archive_index_entry",
        "archive_current_task_command",
        "archive_index_path",
        "archive_list_command",
        "archive_sync_command",
        "archive_task_plan_command",
        "collect_archive_sync_rows",
        "count_by_key",
        "diagnostic_payload",
        "is_authority_path",
        "merge_request_has_required_fields",
        "normalize_scope_path",
        "normalize_scope_values",
        "normalize_typed_scope_values",
        "parse_workstream_index",
        "read_workstream_detail",
        "render_archive_index_table",
        "render_workstream_detail",
        "render_workstream_index",
        "render_workstream_index_text",
        "replace_workstream_entry",
        "resolve_workstream_detail_path",
        "scope_paths_conflict",
        "skipped_missing_generated_archive_details",
        "synced_workstream_entries",
        "update_workstream_detail_metadata",
        "update_workstream_status",
        "workstream_add_command",
        "workstream_archive_candidates_command",
        "workstream_archive_command",
        "workstream_archive_dir",
        "workstream_archive_draft_command",
        "workstream_block_command",
        "workstream_cancel_command",
        "workstream_claim_command",
        "workstream_context_command",
        "workstream_counts",
        "workstream_dashboard_command",
        "workstream_detail_metadata_value",
        "workstream_detail_rel",
        "workstream_details_dir",
        "workstream_done_command",
        "workstream_entry_from_detail",
        "workstream_entry_payload",
        "workstream_focus_command",
        "workstream_front_matter_schema",
        "workstream_guard_command",
        "workstream_id_exists",
        "workstream_index_path",
        "workstream_index_state",
        "workstream_init_command",
        "workstream_initialized",
        "workstream_list_command",
        "workstream_merge_request_command",
        "workstream_merge_start_command",
        "workstream_next_actions_command",
        "workstream_note_command",
        "workstream_preflight_command",
        "workstream_ready_command",
        "workstream_reserve_command",
        "workstream_scope_add_command",
        "workstream_set_command",
        "workstream_show_command",
        "workstream_stage_add_command",
        "workstream_stage_done_command",
        "workstream_stage_list_command",
        "workstream_status_command",
        "workstream_sync_command",
        "workstream_type",
        "workstream_write_scope",
        "write_workstream_index",
    ),
    "check": (
        "check_command",
        "check_context",
        "check_workstream_scope_claims",
        "extract_current_task_status",
        "extract_heading_value",
        "find_workstream_stage_row",
        "meaningful_ref_value",
        "parse_workstream_detail_for_check",
        "read_text",
        "read_workstream_stage_rows",
        "replace_or_append_workstream_stage_rows",
        "require_workstream_stage_belongs_to",
        "status_command",
        "terminal_workstream_stage_status",
        "workstream_section_missing",
        "workstream_stage_belongs_to",
        "workstream_stage_dependency_tokens",
        "workstream_stage_payload",
        "workstream_statuses_for_task_checks",
    ),
    "core": (
        "copy_dynamic_minimal_files",
        "copy_selected_files",
        "ensure_clean_target",
        "human_layer_paths",
        "maybe_check_after",
        "planned_init_files",
        "planned_simplify_files",
        "required_dirs",
        "required_files_for_check",
        "run_with_context_lock",
        "skip_placeholder_check",
        "write_minimal_overrides",
        "write_root_agents",
    ),
    "doctor": ("doctor_command",),
    "knowledge_review": (
        "audit_context_command",
        "collect_review_stale_items",
        "curate_draft_command",
        "knowledge_apply_command",
        "knowledge_draft_command",
        "knowledge_list_command",
        "knowledge_mark_command",
        "knowledge_show_command",
        "knowledge_similarity_messages",
        "knowledge_sync_command",
        "markdown_value",
        "read_feedback_rows",
        "review_stale_command",
    ),
    "objects": (
        "clean_human_index_path_cell",
        "decisions_sync_command",
        "edit_section_append_command",
        "edit_section_get_command",
        "edit_section_replace_command",
        "edit_table_upsert_command",
        "feedback_archive_candidates_command",
        "feedback_archive_command",
        "feedback_done_command",
        "feedback_list_command",
        "feedback_reject_command",
        "feedback_triage_command",
        "human_index_path",
        "human_index_sync_command",
        "human_list_command",
        "human_mark_command",
        "init_command",
        "link_add_command",
        "linkify_command",
        "new_adr_command",
        "new_feedback_command",
        "new_human_note_command",
        "new_reference_command",
        "new_rule_command",
        "new_source_command",
        "new_task_command",
        "new_worklog_command",
        "normalize_items",
        "numbered_list",
        "read_human_index_rows",
        "read_project_versions",
        "render_current_task",
        "simplify_command",
        "slugify_file_stem",
        "version_set_command",
        "version_show_command",
        "writeback_draft_command",
    ),
    "plan_task": (
        "DOCTOR_BACKTICK_PATH_RE",
        "DOCTOR_COMPLETION_TARGET_LINE_RE",
        "DOCTOR_CONTEXT_LINE_THRESHOLD",
        "DOCTOR_CONTEXT_PROCESS_SECTION_RE",
        "DOCTOR_CONTEXT_PROCESS_SIGNALS",
        "DOCTOR_CONTEXT_PROCESS_SIGNAL_LINE_THRESHOLD",
        "DOCTOR_DATA_REF_EXTENSIONS",
        "DOCTOR_LIST_ITEM_RE",
        "DOCTOR_MARKDOWN_LINK_TARGET_RE",
        "DOCTOR_PLAIN_DATA_PATH_RE",
        "DOCTOR_ROOT_OUTPUT_RE",
        "DOCTOR_ROOT_OUTPUT_THRESHOLD",
        "DOCTOR_TERMINAL_WORKSTREAM_EXCESS_THRESHOLD",
        "TERMINAL_SUBTASK_STATUSES",
        "TERMINAL_WORKSTREAM_STATUSES",
        "WORKSTREAM_PROTOCOL_WITHOUT_MERGING",
        "WORKSTREAM_PROTOCOL_WITH_MERGING",
        "current_task_path",
        "dependency_task_ids",
        "plan_add_task_command",
        "plan_complete_command",
        "plan_focus_command",
        "plan_init_command",
        "plan_reference_add_command",
        "plan_reference_list_command",
        "plan_reference_remove_command",
        "plan_set_task_command",
        "plan_stage_add_command",
        "plan_stage_done_command",
        "plan_stage_list_command",
        "plan_stage_set_command",
        "plan_status_command",
        "read_task_rows",
        "read_task_stage_rows",
        "recommended_next_task",
        "render_empty_current_task",
        "task_block_command",
        "task_clear_command",
        "task_done_command",
        "task_plan_path",
        "task_start_command",
    ),
    "upgrade": (
        "Path",
        "render_archive_index",
        "render_empty_task_plan",
        "render_human_index",
        "render_knowledge_index",
        "render_task_plan",
        "upgrade_command",
    ),
}


_MISSING = object()


class RuntimeExportError(ImportError):
    """Raised when the explicit runtime export contract is violated."""


def _component_name(module: Any) -> str:
    return module.__name__.rsplit(".", 1)[-1]


def install_runtime_parts(namespace: dict[str, Any], modules: Sequence[Any]) -> None:
    """Merge the declared exports of ``modules`` into ``namespace`` then share it back.

    ``namespace`` is the runtime module's own globals, so a name that runtime.py
    already defines is validated against the incoming export as well. Merging is
    aborted unless every declaration is satisfiable and collision-free.
    """

    seen: set[str] = set()
    owner: dict[str, str] = {}
    for module in modules:
        component = _component_name(module)
        exports = RUNTIME_PART_EXPORTS.get(component)
        if exports is None:
            raise RuntimeExportError(
                f"{module.__name__} has no entry in RUNTIME_PART_EXPORTS; "
                "declare its exports before adding it to the runtime part modules"
            )
        seen.add(component)
        module_globals = vars(module)
        missing = sorted(name for name in exports if name not in module_globals)
        if missing:
            raise RuntimeExportError(
                f"{component} declares exports that no longer exist: {missing}"
            )
        for name in exports:
            value = module_globals[name]
            existing = namespace.get(name, _MISSING)
            if existing is not _MISSING and existing is not value:
                raise RuntimeExportError(
                    f"runtime namespace conflict for {name!r}: "
                    f"{owner.get(name, 'runtime.py')} and {module.__name__} "
                    "export different objects under the same name"
                )
            owner.setdefault(name, module.__name__)
            namespace[name] = value

    unknown = sorted(set(RUNTIME_PART_EXPORTS) - seen)
    if unknown:
        raise RuntimeExportError(
            f"RUNTIME_PART_EXPORTS declares part modules that are not wired in: {unknown}"
        )

    shared = {
        name: value for name, value in namespace.items() if not name.startswith("__")
    }
    for module in modules:
        vars(module).update(shared)
