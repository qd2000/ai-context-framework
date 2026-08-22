"""Structured, read-only Git worktree status snapshots.

The snapshot is designed for merge planning and promotion protection.  It does
not mutate the repository and keeps index state separate from working-tree
state, including rename metadata and optional ignored-file discovery.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ai_context_framework.git_support import canonical_path, git_output, run_git, semantic_status


SNAPSHOT_SCHEMA_VERSION = "acf.git_worktree_snapshot.v1"


@dataclass(frozen=True)
class GitStatusEntry:
    record_type: str
    path: str
    index_status: str
    worktree_status: str
    original_path: str | None = None
    submodule: str | None = None
    mode_head: str | None = None
    mode_index: str | None = None
    mode_worktree: str | None = None
    oid_head: str | None = None
    oid_index: str | None = None
    rename_score: str | None = None
    stage1_mode: str | None = None
    stage2_mode: str | None = None
    stage3_mode: str | None = None
    stage1_oid: str | None = None
    stage2_oid: str | None = None
    stage3_oid: str | None = None

    @property
    def staged(self) -> bool:
        return self.record_type not in {"untracked", "ignored"} and self.index_status != "."

    @property
    def unstaged(self) -> bool:
        return self.record_type not in {"untracked", "ignored"} and self.worktree_status != "."

    def to_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["comparison_key"] = comparison_key(self.path)
        payload["staged"] = self.staged
        payload["unstaged"] = self.unstaged
        return payload


@dataclass(frozen=True)
class GitPathState:
    path: str
    comparison_key: str
    kind: str
    size: int | None
    mode: int | None
    sha256: str | None
    link_target: str | None = None

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GitSequencerState:
    merge: bool
    cherry_pick: bool
    revert: bool
    rebase_apply: bool
    rebase_merge: bool
    bisect: bool

    @property
    def active(self) -> bool:
        return any(asdict(self).values())

    def to_payload(self) -> dict[str, bool]:
        payload = asdict(self)
        payload["active"] = self.active
        return payload


def normalize_relative_path(value: str) -> str:
    return value.replace("\\", "/")


def comparison_key(value: str) -> str:
    normalized = normalize_relative_path(value)
    return normalized.casefold() if os.name == "nt" else normalized


def parse_porcelain_v2_z(text: str) -> tuple[dict[str, str], list[GitStatusEntry]]:
    """Parse ``git status --porcelain=v2 -z --branch`` output."""

    tokens = text.split("\0")
    headers: dict[str, str] = {}
    entries: list[GitStatusEntry] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        index += 1
        if not token:
            continue
        if token.startswith("# "):
            header = token[2:]
            if " " in header:
                key, value = header.split(" ", 1)
                headers[key] = value
            else:
                headers[header] = ""
            continue
        if token.startswith("1 "):
            parts = token.split(" ", 8)
            if len(parts) != 9:
                raise ValueError(f"invalid ordinary porcelain v2 record: {token!r}")
            xy = parts[1]
            entries.append(
                GitStatusEntry(
                    record_type="ordinary",
                    path=normalize_relative_path(parts[8]),
                    index_status=xy[0],
                    worktree_status=xy[1],
                    submodule=parts[2],
                    mode_head=parts[3],
                    mode_index=parts[4],
                    mode_worktree=parts[5],
                    oid_head=parts[6],
                    oid_index=parts[7],
                )
            )
            continue
        if token.startswith("2 "):
            parts = token.split(" ", 9)
            if len(parts) != 10 or index >= len(tokens):
                raise ValueError(f"invalid rename porcelain v2 record: {token!r}")
            original_path = tokens[index]
            index += 1
            xy = parts[1]
            entries.append(
                GitStatusEntry(
                    record_type="rename",
                    path=normalize_relative_path(parts[9]),
                    original_path=normalize_relative_path(original_path),
                    index_status=xy[0],
                    worktree_status=xy[1],
                    submodule=parts[2],
                    mode_head=parts[3],
                    mode_index=parts[4],
                    mode_worktree=parts[5],
                    oid_head=parts[6],
                    oid_index=parts[7],
                    rename_score=parts[8],
                )
            )
            continue
        if token.startswith("u "):
            parts = token.split(" ", 10)
            if len(parts) != 11:
                raise ValueError(f"invalid unmerged porcelain v2 record: {token!r}")
            xy = parts[1]
            entries.append(
                GitStatusEntry(
                    record_type="unmerged",
                    path=normalize_relative_path(parts[10]),
                    index_status=xy[0],
                    worktree_status=xy[1],
                    submodule=parts[2],
                    mode_worktree=parts[6],
                    stage1_mode=parts[3],
                    stage2_mode=parts[4],
                    stage3_mode=parts[5],
                    stage1_oid=parts[7],
                    stage2_oid=parts[8],
                    stage3_oid=parts[9],
                )
            )
            continue
        if token.startswith("? "):
            entries.append(
                GitStatusEntry(
                    record_type="untracked",
                    path=normalize_relative_path(token[2:]),
                    index_status="?",
                    worktree_status="?",
                )
            )
            continue
        if token.startswith("! "):
            entries.append(
                GitStatusEntry(
                    record_type="ignored",
                    path=normalize_relative_path(token[2:]),
                    index_status="!",
                    worktree_status="!",
                )
            )
            continue
        raise ValueError(f"unsupported porcelain v2 record: {token!r}")

    entries.sort(key=lambda row: (comparison_key(row.path), row.record_type, row.original_path or ""))
    return headers, entries


def capture_git_worktree_snapshot(
    root: str | Path,
    *,
    include_ignored: bool = False,
    timestamp: str | None = None,
) -> dict[str, Any]:
    checkout = canonical_path(root)
    status = run_git(
        checkout,
        (
            "status",
            "--porcelain=v2",
            "-z",
            "--branch",
            "--untracked-files=all",
        ),
    )
    headers, entries = parse_porcelain_v2_z(status.stdout)

    if include_ignored:
        ignored = run_git(
            checkout,
            ("ls-files", "--others", "--ignored", "--exclude-standard", "-z"),
        ).stdout
        existing = {(row.record_type, comparison_key(row.path)) for row in entries}
        for raw_path in ignored.split("\0"):
            if not raw_path:
                continue
            path = normalize_relative_path(raw_path)
            identity = ("ignored", comparison_key(path))
            if identity in existing:
                continue
            entries.append(
                GitStatusEntry(
                    record_type="ignored",
                    path=path,
                    index_status="!",
                    worktree_status="!",
                )
            )
            existing.add(identity)
        entries.sort(key=lambda row: (comparison_key(row.path), row.record_type, row.original_path or ""))

    path_states = _capture_path_states(checkout, entries)
    sequencer = capture_git_sequencer_state(checkout)
    now = timestamp or datetime.now(timezone.utc).isoformat()
    branch = headers.get("branch.head") or git_output(checkout, "branch", "--show-current")
    head = headers.get("branch.oid") or git_output(checkout, "rev-parse", "HEAD")
    if head == "(initial)":
        head = None

    entry_payloads = [entry.to_payload() for entry in entries]
    path_payloads = [state.to_payload() for state in path_states]
    staged_paths = sorted({entry.path for entry in entries if entry.staged}, key=comparison_key)
    unstaged_paths = sorted({entry.path for entry in entries if entry.unstaged}, key=comparison_key)
    untracked_paths = sorted(
        {entry.path for entry in entries if entry.record_type == "untracked"},
        key=comparison_key,
    )
    ignored_paths = sorted(
        {entry.path for entry in entries if entry.record_type == "ignored"},
        key=comparison_key,
    )
    unmerged_paths = sorted(
        {entry.path for entry in entries if entry.record_type == "unmerged"},
        key=comparison_key,
    )
    stat_only_paths = [str(value) for value in semantic_status(checkout)["stat_only_paths"]]

    stable_payload: dict[str, Any] = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "checkout": str(checkout),
        "branch": branch,
        "head": head,
        "include_ignored": include_ignored,
        "entries": entry_payloads,
        "path_states": path_payloads,
        "staged_paths": staged_paths,
        "unstaged_paths": unstaged_paths,
        "untracked_paths": untracked_paths,
        "ignored_paths": ignored_paths,
        "unmerged_paths": unmerged_paths,
        "stat_only_paths": stat_only_paths,
        "index_lock": _git_path_exists(checkout, "index.lock"),
        "sequencer": sequencer.to_payload(),
    }
    fingerprint = hashlib.sha256(
        json.dumps(
            stable_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return {
        **stable_payload,
        "fingerprint": fingerprint,
        "captured_at": now,
    }


def capture_git_sequencer_state(root: str | Path) -> GitSequencerState:
    checkout = canonical_path(root)
    return GitSequencerState(
        merge=_git_path_exists(checkout, "MERGE_HEAD"),
        cherry_pick=_git_path_exists(checkout, "CHERRY_PICK_HEAD"),
        revert=_git_path_exists(checkout, "REVERT_HEAD"),
        rebase_apply=_git_path_exists(checkout, "rebase-apply"),
        rebase_merge=_git_path_exists(checkout, "rebase-merge"),
        bisect=_git_path_exists(checkout, "BISECT_LOG"),
    )


def _capture_path_states(
    checkout: Path,
    entries: list[GitStatusEntry],
) -> list[GitPathState]:
    paths: dict[str, str] = {}
    for entry in entries:
        paths.setdefault(comparison_key(entry.path), entry.path)
        if entry.original_path:
            paths.setdefault(comparison_key(entry.original_path), entry.original_path)
    states = [_inspect_path(checkout, path) for _, path in sorted(paths.items())]
    return states


def _inspect_path(checkout: Path, relative_path: str) -> GitPathState:
    path = checkout / Path(relative_path)
    key = comparison_key(relative_path)
    if path.is_symlink():
        target = os.readlink(path)
        digest = hashlib.sha256(target.encode("utf-8", errors="surrogatepass")).hexdigest()
        mode = stat.S_IMODE(path.lstat().st_mode)
        return GitPathState(relative_path, key, "symlink", len(target), mode, digest, target)
    if path.is_file():
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
        file_stat = path.stat()
        return GitPathState(
            relative_path,
            key,
            "file",
            file_stat.st_size,
            stat.S_IMODE(file_stat.st_mode),
            digest.hexdigest(),
        )
    if path.is_dir():
        directory_stat = path.stat()
        return GitPathState(
            relative_path,
            key,
            "directory",
            None,
            stat.S_IMODE(directory_stat.st_mode),
            None,
        )
    return GitPathState(relative_path, key, "missing", None, None, None)


def _git_path_exists(checkout: Path, git_path_name: str) -> bool:
    raw = git_output(checkout, "rev-parse", "--git-path", git_path_name)
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = checkout / candidate
    return candidate.exists()
