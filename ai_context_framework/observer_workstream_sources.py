"""Git-lineage helpers for Observer Workstream authority sources."""

from __future__ import annotations

from pathlib import Path

from ai_context_framework.git_support import is_ancestor, path_key, run_git


def _source_path_clean(
    worktree: dict[str, object] | None,
    source: dict[str, object] | None,
) -> bool:
    """Return whether one Workstream authority file is unchanged in a worktree."""

    if worktree is None or source is None:
        return False
    root_raw = worktree.get("path")
    detail_raw = source.get("detail_path")
    if not isinstance(root_raw, str) or not isinstance(detail_raw, str):
        return False
    try:
        relative = Path(detail_raw).resolve().relative_to(Path(root_raw).resolve()).as_posix()
    except (OSError, ValueError):
        return False
    dirty_paths: set[str] = set()
    for key in ("staged_paths", "unstaged_paths", "unmerged_paths"):
        for value in worktree.get(key) or []:
            if isinstance(value, str):
                dirty_paths.add(value.replace("\\", "/"))
    return relative not in dirty_paths


def _primary_authority_unchanged_since_common_base(
    project_root: Path,
    *,
    primary_head: str,
    selected_head: str,
    primary_source: dict[str, object],
) -> bool:
    detail_raw = primary_source.get("detail_path")
    if not isinstance(detail_raw, str):
        return False
    try:
        relative = Path(detail_raw).resolve().relative_to(project_root.resolve()).as_posix()
    except (OSError, ValueError):
        return False
    base_result = run_git(project_root, ("merge-base", primary_head, selected_head), check=False)
    common_base = base_result.stdout.strip()
    if base_result.returncode != 0 or not common_base:
        return False
    diff_result = run_git(
        project_root,
        ("diff", "--quiet", common_base, primary_head, "--", relative),
        check=False,
    )
    return diff_result.returncode == 0


def active_registered_workstream_lineage_basis(
    project_root: Path,
    *,
    registry: dict[str, object],
    primary_key: str,
    selected_key: str,
    sources: list[dict[str, object]],
    primary_worktree: dict[str, object] | None,
    selected_worktree: dict[str, object] | None,
) -> str | None:
    """Return a consistency basis for ordered active-Workstream lineage.

    Long-lived maintenance can continue on the registered branch after that
    branch was merged to primary.  The primary merge commit is then not an
    ancestor of the continuing branch.  If primary made no independent change
    to the same Workstream authority path after their common base, the branch
    remains ordered authority rather than a contradictory source.
    """

    if str(registry.get("state") or "").casefold() != "active":
        return None
    source_keys = {
        path_key(str(row["source_worktree"]))
        for row in sources
        if row.get("source_worktree")
    }
    if not source_keys <= {primary_key, selected_key}:
        return None
    primary_head = primary_worktree.get("head") if primary_worktree else None
    selected_head = selected_worktree.get("head") if selected_worktree else None
    if not isinstance(primary_head, str) or not primary_head:
        return None
    if not isinstance(selected_head, str) or not selected_head:
        return None
    primary_source = next(
        (
            row
            for row in sources
            if isinstance(row.get("source_worktree"), str)
            and path_key(str(row["source_worktree"])) == primary_key
        ),
        None,
    )
    if not _source_path_clean(primary_worktree, primary_source):
        return None
    if is_ancestor(project_root, primary_head, selected_head):
        return "active_registered_worktree_descends_clean_primary"
    if primary_source is not None and _primary_authority_unchanged_since_common_base(
        project_root,
        primary_head=primary_head,
        selected_head=selected_head,
        primary_source=primary_source,
    ):
        return "active_registered_worktree_post_merge_continuation"
    return None
