"""Explicit runtime context for command modules that read the shared namespace.

``commands/workstream.py`` and ``commands/workstream_reserve.py`` used to receive
``WorkstreamDependencies(symbols=globals())`` — the entire merged runtime
namespace — and copy it into their own module globals on **every** handler
invocation. Both modules only ever read a small, stable subset of that namespace,
so this module replaces the wholesale copy with a bounded, frozen context
containing exactly the names they use.

``scripts/runtime_export_audit.py`` recomputes both tuples from the source and
``tests/test_runtime_contracts.py`` compares them, so a newly referenced name
cannot silently fall outside the context: the build fails closed instead.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence


WORKSTREAM_CONSUMER_NAMES: tuple[str, ...] = (
    "ACTIVE_WORKSTREAM_STATUSES",
    "DATE_RE",
    "EXIT_CHECK_FAILED",
    "JSON_SCHEMA_VERSION",
    "WORKSTREAM_ARCHIVE_DIR_REL",
    "WORKSTREAM_ID_TOKEN_RE",
    "WORKSTREAM_INDEX_REL",
    "WORKSTREAM_METADATA_FIELDS",
    "WORKSTREAM_NOTE_SECTIONS",
    "WORKSTREAM_STATE_TRANSITIONS",
    "append_archive_index_entry",
    "append_or_create_section",
    "archive_index_path",
    "check_workstream_scope_claims",
    "datetime",
    "diagnostic_payload",
    "dry_run_enabled",
    "emit_write_result",
    "error_next_actions",
    "extract_heading_value",
    "find_workstream_stage_row",
    "fnmatch",
    "format_front_matter",
    "has_workstream_archive_marker",
    "infer_project_root",
    "is_authority_path",
    "is_relative_to",
    "json_enabled",
    "maybe_check_after",
    "meaningful_ref_value",
    "normalize_scope_path",
    "normalize_scope_values",
    "normalize_typed_scope_values",
    "parse_workstream_index",
    "print_json",
    "read_edit_input",
    "read_task_stage_rows",
    "read_text",
    "read_workstream_detail",
    "read_workstream_stage_rows",
    "relative_display_path",
    "render_archive_index",
    "render_workstream_detail",
    "render_workstream_index",
    "render_workstream_index_text",
    "replace_or_append_section",
    "replace_or_append_workstream_stage_rows",
    "replace_workstream_entry",
    "require_context_root",
    "require_workstream_stage_belongs_to",
    "required_field_missing",
    "safe_section_body_from_text",
    "set_result_payload",
    "slugify_file_stem",
    "split_typed_scope",
    "subprocess",
    "subsection_body",
    "synced_workstream_entries",
    "task_plan_path",
    "terminal_workstream_stage_status",
    "update_workstream_detail_metadata",
    "update_workstream_status",
    "validate_scope_path",
    "workstream_archive_dir",
    "workstream_archive_marker",
    "workstream_counts",
    "workstream_detail_metadata_value",
    "workstream_detail_rel",
    "workstream_details_dir",
    "workstream_entry_from_detail",
    "workstream_entry_payload",
    "workstream_id_exists",
    "workstream_index_path",
    "workstream_index_state",
    "workstream_initialized",
    "workstream_section_missing",
    "workstream_stage_belongs_to",
    "workstream_stage_dependency_tokens",
    "workstream_stage_payload",
    "workstream_type",
    "workstream_write_scope",
    "write_workstream_index",
)


WORKSTREAM_RESERVE_CONSUMER_NAMES: tuple[str, ...] = (
    "check_context",
    "infer_context_profile",
    "normalized_read_claim",
    "normalized_write_claim",
    "parse_workstream_index",
    "render_workstream_detail",
    "render_workstream_index_text",
    "require_context_root",
    "workstream_detail_rel",
    "workstream_details_dir",
    "workstream_index_path",
    "workstream_write_scope",
    "write_workstream_index",
)


class RuntimeContextError(RuntimeError):
    """Raised when a bounded context cannot be built from the requested names."""


@dataclass(frozen=True)
class RuntimeContext:
    """A frozen, explicitly bounded view of the shared runtime namespace."""

    label: str
    names: Mapping[str, Any]

    def resolve(self, name: str) -> Any:
        try:
            return self.names[name]
        except KeyError as exc:
            raise RuntimeContextError(
                f"{self.label}: {name!r} is not part of this context"
            ) from exc

    def as_binding(self) -> dict[str, Any]:
        """Return the mapping passed to a consumer's ``_bind``."""

        return dict(self.names)


def build_runtime_context(
    namespace: Mapping[str, Any],
    required: Sequence[str],
    *,
    label: str,
    extra_providers: Sequence[Mapping[str, Any]] = (),
) -> RuntimeContext:
    """Select exactly ``required`` from ``namespace`` (plus optional extra providers).

    ``extra_providers`` are searched first and are used where a consumer's names
    come from more than one module. A name that no provider supplies fails closed
    rather than silently widening the context.
    """

    merged: dict[str, Any] = {}
    for provider in extra_providers:
        merged.update(provider)
    merged.update(namespace)
    missing = sorted(name for name in required if name not in merged)
    if missing:
        raise RuntimeContextError(f"{label}: required names are not available: {missing}")
    return RuntimeContext(label=label, names={name: merged[name] for name in required})
