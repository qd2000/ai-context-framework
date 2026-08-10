"""Candidate tree discovery and primary-worktree collision analysis.

The functions in this module are read-only.  They compare a merge candidate
against a structured primary checkout snapshot without modifying either the
primary checkout or a task worktree.
"""

from __future__ import annotations

import hashlib
import os
import stat
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from ai_context_framework.git_support import canonical_path, merge_tree, run_git
from ai_context_framework.worktree_status import comparison_key, normalize_relative_path


CANDIDATE_SCHEMA_VERSION = "acf.git_merge_candidate.v1"
COLLISION_SCHEMA_VERSION = "acf.git_collision_report.v1"


@dataclass(frozen=True)
class CandidatePathChange:
    status: str
    path: str
    original_path: str | None
    old_mode: str
    new_mode: str
    old_oid: str
    new_oid: str

    @property
    def status_code(self) -> str:
        return self.status[:1]

    @property
    def affected_paths(self) -> tuple[str, ...]:
        if self.original_path and self.original_path != self.path:
            return (self.original_path, self.path)
        return (self.path,)

    def to_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["status_code"] = self.status_code
        payload["affected_paths"] = list(self.affected_paths)
        payload["comparison_keys"] = [comparison_key(path) for path in self.affected_paths]
        return payload


def parse_raw_diff_z(text: str) -> list[CandidatePathChange]:
    """Parse ``git diff-tree --raw -z -M -C`` output."""

    tokens = text.split("\0")
    changes: list[CandidatePathChange] = []
    index = 0
    while index < len(tokens):
        meta = tokens[index]
        index += 1
        if not meta:
            continue
        if not meta.startswith(":"):
            raise ValueError(f"invalid raw diff record: {meta!r}")
        fields = meta[1:].split()
        if len(fields) != 5:
            raise ValueError(f"invalid raw diff metadata: {meta!r}")
        old_mode, new_mode, old_oid, new_oid, status = fields
        if index >= len(tokens):
            raise ValueError("raw diff record missing path")
        first_path = normalize_relative_path(tokens[index])
        index += 1
        status_code = status[:1]
        if status_code in {"R", "C"}:
            if index >= len(tokens):
                raise ValueError("rename/copy raw diff record missing destination path")
            destination = normalize_relative_path(tokens[index])
            index += 1
            original = first_path
            path = destination
        else:
            original = None
            path = first_path
        changes.append(
            CandidatePathChange(
                status=status,
                path=path,
                original_path=original,
                old_mode=old_mode,
                new_mode=new_mode,
                old_oid=old_oid,
                new_oid=new_oid,
            )
        )
    changes.sort(
        key=lambda row: (
            comparison_key(row.path),
            comparison_key(row.original_path or ""),
            row.status,
        )
    )
    return changes


def build_candidate_preview(
    repo: str | Path,
    *,
    primary_head: str,
    source_head: str,
) -> dict[str, Any]:
    repository = canonical_path(repo)
    preview = merge_tree(repository, primary_head, source_head)
    if not preview["ok"]:
        return {
            "schema_version": CANDIDATE_SCHEMA_VERSION,
            "ok": False,
            "primary_head": primary_head,
            "source_head": source_head,
            "tree": None,
            "changes": [],
            "changed_paths": [],
            "merge_preview": preview,
        }
    tree = preview.get("tree")
    if not isinstance(tree, str) or not tree:
        raise SystemExit("merge_candidate_tree_missing")
    raw = run_git(
        repository,
        (
            "diff-tree",
            "--raw",
            "-z",
            "--no-commit-id",
            "-r",
            "-M",
            "-C",
            primary_head,
            tree,
        ),
    ).stdout
    changes = parse_raw_diff_z(raw)
    changed_paths = sorted(
        {path for change in changes for path in change.affected_paths},
        key=comparison_key,
    )
    return {
        "schema_version": CANDIDATE_SCHEMA_VERSION,
        "ok": True,
        "primary_head": primary_head,
        "source_head": source_head,
        "tree": tree,
        "changes": [change.to_payload() for change in changes],
        "changed_paths": changed_paths,
        "merge_preview": preview,
    }


def build_candidate_from_tip(
    repo: str | Path,
    *,
    primary_head: str,
    candidate_tip: str,
    source_head: str | None = None,
) -> dict[str, Any]:
    repository = canonical_path(repo)
    raw = run_git(
        repository,
        (
            "diff-tree",
            "--raw",
            "-z",
            "--no-commit-id",
            "-r",
            "-M",
            "-C",
            primary_head,
            candidate_tip,
        ),
    ).stdout
    changes = parse_raw_diff_z(raw)
    changed_paths = sorted(
        {path for change in changes for path in change.affected_paths},
        key=comparison_key,
    )
    return {
        "schema_version": CANDIDATE_SCHEMA_VERSION,
        "ok": True,
        "primary_head": primary_head,
        "source_head": source_head,
        "tree": candidate_tip,
        "candidate_tip": candidate_tip,
        "changes": [change.to_payload() for change in changes],
        "changed_paths": changed_paths,
        "merge_preview": {"ok": True, "mode": "integration_tip", "tree": candidate_tip},
    }


def analyze_primary_collisions(
    repo: str | Path,
    *,
    snapshot: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> dict[str, Any]:
    """Classify primary local paths against a candidate merge tree.

    Exact overlaps may be accepted only when every relevant local layer matches
    the candidate final blob/type.  Structural parent/child overlaps are kept
    conservative and are reported as divergent.
    """

    if not candidate.get("ok"):
        return {
            "schema_version": COLLISION_SCHEMA_VERSION,
            "allowed": False,
            "branch_conflict": True,
            "identical_overlap_paths": [],
            "divergent_overlap_paths": [],
            "collisions": [],
            "recommended_action": "integration_conflict_resolution",
        }

    repository = canonical_path(repo)
    tree = str(candidate["tree"])
    changes = [_change_from_payload(row) for row in candidate.get("changes", [])]
    local_entries = [dict(row) for row in snapshot.get("entries", []) if isinstance(row, Mapping)]
    local_states = {
        str(row.get("comparison_key")): row
        for row in snapshot.get("path_states", [])
        if isinstance(row, Mapping) and row.get("comparison_key")
    }
    _add_candidate_relevant_ignored(repository, changes, local_entries, local_states)
    local_paths = _local_paths(local_entries)
    changes_by_key: dict[str, list[CandidatePathChange]] = {}
    for change in changes:
        for path in change.affected_paths:
            changes_by_key.setdefault(comparison_key(path), []).append(change)

    collisions: list[dict[str, Any]] = []
    identical: set[str] = set()
    divergent: set[str] = set()

    for local_path in sorted(local_paths, key=comparison_key):
        local_key = comparison_key(local_path)
        exact_changes = changes_by_key.get(local_key, [])
        if exact_changes:
            result = _analyze_exact_overlap(
                repository,
                tree=tree,
                local_path=local_path,
                entries=[row for row in local_entries if _entry_mentions(row, local_key)],
                path_state=local_states.get(local_key),
                changes=exact_changes,
            )
            collisions.append(result)
            if result["classification"] == "identical":
                identical.add(local_path)
            else:
                divergent.add(local_path)
            continue

        structural = _structural_candidate_paths(local_key, changes)
        if structural:
            divergent.add(local_path)
            collisions.append(
                {
                    "path": local_path,
                    "comparison_key": local_key,
                    "classification": "divergent",
                    "reason": "parent_child_or_casefold_collision",
                    "candidate_paths": structural,
                }
            )

    collisions.sort(key=lambda row: (str(row.get("comparison_key")), str(row.get("reason"))))
    return {
        "schema_version": COLLISION_SCHEMA_VERSION,
        "allowed": not divergent,
        "branch_conflict": False,
        "identical_overlap_paths": sorted(identical, key=comparison_key),
        "divergent_overlap_paths": sorted(divergent, key=comparison_key),
        "collisions": collisions,
        "recommended_action": "promote" if not divergent else "wait_or_resolve_primary_paths",
    }


def _change_from_payload(row: Mapping[str, Any]) -> CandidatePathChange:
    return CandidatePathChange(
        status=str(row.get("status") or ""),
        path=normalize_relative_path(str(row.get("path") or "")),
        original_path=(
            normalize_relative_path(str(row["original_path"]))
            if row.get("original_path")
            else None
        ),
        old_mode=str(row.get("old_mode") or "000000"),
        new_mode=str(row.get("new_mode") or "000000"),
        old_oid=str(row.get("old_oid") or "0" * 40),
        new_oid=str(row.get("new_oid") or "0" * 40),
    )


def _add_candidate_relevant_ignored(
    repo: Path,
    changes: list[CandidatePathChange],
    entries: list[dict[str, Any]],
    states: dict[str, Mapping[str, Any]],
) -> None:
    pathspecs = sorted(
        {path for change in changes for path in change.affected_paths},
        key=comparison_key,
    )
    if not pathspecs:
        return
    output = run_git(
        repo,
        (
            "ls-files",
            "--others",
            "--ignored",
            "--exclude-standard",
            "-z",
            "--",
            *pathspecs,
        ),
        check=False,
    ).stdout
    known = {comparison_key(str(row.get("path") or "")) for row in entries}
    relevant = {normalize_relative_path(value) for value in output.split("\0") if value}
    for path in pathspecs:
        candidate = repo / Path(path)
        if candidate.exists() and comparison_key(path) not in known:
            tracked = run_git(repo, ("ls-files", "--error-unmatch", "--", path), check=False)
            ignored = run_git(repo, ("check-ignore", "-q", "--", path), check=False)
            if tracked.returncode != 0 and ignored.returncode == 0:
                relevant.add(path)
    for path in sorted(relevant, key=comparison_key):
        key = comparison_key(path)
        if key in known:
            continue
        entries.append(
            {
                "record_type": "ignored",
                "path": path,
                "original_path": None,
                "index_status": "!",
                "worktree_status": "!",
                "staged": False,
                "unstaged": False,
                "comparison_key": key,
            }
        )
        states[key] = _inspect_local_path(repo, path)
        known.add(key)


def _inspect_local_path(repo: Path, relative_path: str) -> dict[str, Any]:
    path = repo / Path(relative_path)
    key = comparison_key(relative_path)
    if path.is_symlink():
        target = os.readlink(path)
        return {
            "path": relative_path,
            "comparison_key": key,
            "kind": "symlink",
            "size": len(target),
            "mode": stat.S_IMODE(path.lstat().st_mode),
            "sha256": hashlib.sha256(target.encode("utf-8", errors="surrogatepass")).hexdigest(),
            "link_target": target,
        }
    if path.is_file():
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        info = path.stat()
        return {
            "path": relative_path,
            "comparison_key": key,
            "kind": "file",
            "size": info.st_size,
            "mode": stat.S_IMODE(info.st_mode),
            "sha256": digest.hexdigest(),
            "link_target": None,
        }
    if path.is_dir():
        info = path.stat()
        return {
            "path": relative_path,
            "comparison_key": key,
            "kind": "directory",
            "size": None,
            "mode": stat.S_IMODE(info.st_mode),
            "sha256": None,
            "link_target": None,
        }
    return {
        "path": relative_path,
        "comparison_key": key,
        "kind": "missing",
        "size": None,
        "mode": None,
        "sha256": None,
        "link_target": None,
    }


def _local_paths(entries: Iterable[Mapping[str, Any]]) -> set[str]:
    paths: set[str] = set()
    for entry in entries:
        path = entry.get("path")
        if isinstance(path, str) and path:
            paths.add(normalize_relative_path(path))
        original = entry.get("original_path")
        if isinstance(original, str) and original:
            paths.add(normalize_relative_path(original))
    return paths


def _entry_mentions(entry: Mapping[str, Any], local_key: str) -> bool:
    for name in ("path", "original_path"):
        value = entry.get(name)
        if isinstance(value, str) and comparison_key(value) == local_key:
            return True
    return False


def _analyze_exact_overlap(
    repo: Path,
    *,
    tree: str,
    local_path: str,
    entries: list[Mapping[str, Any]],
    path_state: Mapping[str, Any] | None,
    changes: list[CandidatePathChange],
) -> dict[str, Any]:
    candidate_state = _candidate_path_state(repo, tree, local_path)
    local_layers: list[dict[str, Any]] = []
    for entry in entries:
        record_type = str(entry.get("record_type") or "")
        staged = bool(entry.get("staged"))
        unstaged = bool(entry.get("unstaged"))
        if staged:
            local_layers.append(
                {
                    "layer": "index",
                    "oid": entry.get("oid_index"),
                    "mode": entry.get("mode_index"),
                    "matches": _layer_matches_candidate(
                        candidate_state,
                        oid=entry.get("oid_index"),
                        mode=entry.get("mode_index"),
                        missing=str(entry.get("index_status")) == "D",
                    ),
                }
            )
        if unstaged or record_type in {"untracked", "ignored"}:
            worktree_oid, worktree_mode, worktree_missing = _working_tree_identity(
                repo, local_path, path_state
            )
            local_layers.append(
                {
                    "layer": "worktree",
                    "oid": worktree_oid,
                    "mode": worktree_mode,
                    "matches": _layer_matches_candidate(
                        candidate_state,
                        oid=worktree_oid,
                        mode=worktree_mode,
                        missing=worktree_missing,
                    ),
                }
            )
    if not local_layers:
        worktree_oid, worktree_mode, worktree_missing = _working_tree_identity(
            repo, local_path, path_state
        )
        local_layers.append(
            {
                "layer": "worktree",
                "oid": worktree_oid,
                "mode": worktree_mode,
                "matches": _layer_matches_candidate(
                    candidate_state,
                    oid=worktree_oid,
                    mode=worktree_mode,
                    missing=worktree_missing,
                ),
            }
        )
    matches = all(bool(row["matches"]) for row in local_layers)
    return {
        "path": local_path,
        "comparison_key": comparison_key(local_path),
        "classification": "identical" if matches else "divergent",
        "reason": "all_local_layers_match_candidate" if matches else "local_content_or_type_differs",
        "candidate_state": candidate_state,
        "local_layers": local_layers,
        "candidate_changes": [change.to_payload() for change in changes],
    }


def _candidate_path_state(repo: Path, tree: str, path: str) -> dict[str, Any]:
    result = run_git(repo, ("ls-tree", "-z", tree, "--", path), check=False)
    if result.returncode != 0 or not result.stdout:
        return {"kind": "missing", "mode": None, "oid": None}
    token = result.stdout.split("\0", 1)[0]
    if "\t" not in token:
        return {"kind": "missing", "mode": None, "oid": None}
    metadata, returned_path = token.split("\t", 1)
    if comparison_key(returned_path) != comparison_key(path):
        return {"kind": "missing", "mode": None, "oid": None}
    mode, object_type, oid = metadata.split(" ", 2)
    kind = "directory" if object_type == "tree" else "symlink" if mode == "120000" else "file"
    return {"kind": kind, "mode": mode, "oid": oid}


def _working_tree_identity(
    repo: Path,
    path: str,
    path_state: Mapping[str, Any] | None,
) -> tuple[str | None, str | None, bool]:
    kind = str(path_state.get("kind")) if path_state else "missing"
    if kind == "missing":
        return None, None, True
    if kind == "directory":
        return None, "040000", False
    result = run_git(repo, ("hash-object", "--no-filters", "--", path), check=False)
    oid = result.stdout.strip() if result.returncode == 0 else None
    mode = "120000" if kind == "symlink" else "100755" if _is_executable(path_state) else "100644"
    return oid, mode, False


def _is_executable(path_state: Mapping[str, Any] | None) -> bool:
    if not path_state:
        return False
    mode = path_state.get("mode")
    return isinstance(mode, int) and bool(mode & 0o111)


def _layer_matches_candidate(
    candidate: Mapping[str, Any],
    *,
    oid: object,
    mode: object,
    missing: bool,
) -> bool:
    if candidate.get("kind") == "missing":
        return missing
    if missing:
        return False
    candidate_mode = candidate.get("mode")
    candidate_oid = candidate.get("oid")
    return isinstance(oid, str) and oid == candidate_oid and isinstance(mode, str) and mode == candidate_mode


def _structural_candidate_paths(
    local_key: str,
    changes: Iterable[CandidatePathChange],
) -> list[str]:
    result: set[str] = set()
    for change in changes:
        for candidate_path in change.affected_paths:
            candidate_key = comparison_key(candidate_path)
            if candidate_key == local_key:
                continue
            if candidate_key.startswith(local_key + "/") or local_key.startswith(candidate_key + "/"):
                result.add(candidate_path)
            elif os.name == "nt" and normalize_relative_path(candidate_path) != normalize_relative_path(local_key) and candidate_key == local_key:
                result.add(candidate_path)
    return sorted(result, key=comparison_key)
