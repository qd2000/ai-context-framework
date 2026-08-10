"""Git discovery, configuration, locking, registry, and operation journals.

This module intentionally depends only on the Python standard library.  It is
loaded only by the optional ``acf worktree`` and ``acf workstream reserve``
commands, so projects that only use the existing context/Workstream commands do
not acquire a Git or worktree requirement.
"""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from ai_context_framework.observability import atomic_write_text
from ai_context_framework.paths import discover_context, infer_project_root


ALLOWED_NON_WORKSTREAM_KINDS = (
    "bugfix",
    "docs",
    "experiment",
    "investigation",
    "maintenance",
    "refactor",
    "release",
)
LOW_INFORMATION_SLUGS = {
    "backup",
    "fix",
    "new",
    "temp",
    "temporary",
    "test",
    "tmp",
    "worktree",
    "worktree1",
}
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
WORKSTREAM_TOKEN_RE = re.compile(r"WS(\d{3,})", re.IGNORECASE)


@dataclass(frozen=True)
class GitCommandResult:
    argv: tuple[str, ...]
    cwd: str
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class WorktreeRecord:
    path: Path
    head: str | None
    branch: str | None
    detached: bool
    bare: bool
    prunable: str | None

    @property
    def branch_short(self) -> str | None:
        prefix = "refs/heads/"
        if self.branch and self.branch.startswith(prefix):
            return self.branch[len(prefix) :]
        return self.branch


@dataclass(frozen=True)
class GitProjectConfig:
    primary_checkout: Path
    primary_branch: str
    worktree_root: Path
    branch_prefix: str = "codex"
    workstream_branch_template: str = "{branch_prefix}/{workstream_lower}-{slug}"
    workstream_worktree_template: str = "{worktree_root}/{workstream_lower}-{slug}"
    non_workstream_branch_template: str = "{branch_prefix}/{kind}-{slug}"
    non_workstream_worktree_template: str = "{worktree_root}/{kind}-{slug}"
    sync_strategy: str = "merge"
    merge_strategy: str = "no-ff"
    primary_dirty_policy: str = "allow_non_overlapping"
    artifact_cache_patterns: tuple[str, ...] = ()
    artifact_discardable_patterns: tuple[str, ...] = ()
    config_path: Path | None = None


@dataclass(frozen=True)
class GitProject:
    context_root: Path
    project_root: Path
    repo_root: Path
    common_dir: Path
    config: GitProjectConfig


@dataclass(frozen=True)
class WorktreeTarget:
    key: str
    branch: str
    path: Path
    base_branch: str
    base_commit: str
    workstream_id: str | None = None
    kind: str | None = None
    slug: str | None = None
    reservation_path: str | None = None
    reservation_commit: str | None = None


class GitCommandError(SystemExit):
    def __init__(self, result: GitCommandResult):
        self.result = result
        detail = result.stderr.strip() or result.stdout.strip() or "git command failed"
        super().__init__(f"git_command_failed: {detail}")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_path(path: str | Path) -> Path:
    return Path(path).expanduser().resolve()


def path_key(path: str | Path) -> str:
    value = str(canonical_path(path)).replace("\\", "/")
    return value.casefold() if os.name == "nt" else value


def run_git(
    cwd: str | Path,
    args: Sequence[str],
    *,
    check: bool = True,
    env: Mapping[str, str] | None = None,
) -> GitCommandResult:
    argv = ("git", *tuple(str(value) for value in args))
    completed = subprocess.run(
        argv,
        cwd=str(canonical_path(cwd)),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=dict(env) if env is not None else None,
        shell=False,
        check=False,
    )
    result = GitCommandResult(
        argv=tuple(argv),
        cwd=str(canonical_path(cwd)),
        returncode=int(completed.returncode),
        stdout=completed.stdout,
        stderr=completed.stderr,
    )
    if check and result.returncode != 0:
        raise GitCommandError(result)
    return result


def git_output(cwd: str | Path, *args: str) -> str:
    return run_git(cwd, args).stdout.strip()


def git_toplevel(path: str | Path) -> Path:
    try:
        value = git_output(path, "rev-parse", "--show-toplevel")
    except GitCommandError as exc:
        raise SystemExit(f"git_repository_not_found: {canonical_path(path)}") from exc
    return canonical_path(value)


def git_common_dir(path: str | Path) -> Path:
    try:
        value = git_output(path, "rev-parse", "--path-format=absolute", "--git-common-dir")
    except GitCommandError:
        value = git_output(path, "rev-parse", "--git-common-dir")
        candidate = Path(value)
        if not candidate.is_absolute():
            candidate = git_toplevel(path) / candidate
        return canonical_path(candidate)
    return canonical_path(value)


def ref_exists(repo: str | Path, ref: str) -> bool:
    return run_git(repo, ("show-ref", "--verify", "--quiet", ref), check=False).returncode == 0


def branch_exists(repo: str | Path, branch: str) -> bool:
    return ref_exists(repo, f"refs/heads/{branch}")


def rev_parse(repo: str | Path, ref: str) -> str:
    try:
        return git_output(repo, "rev-parse", "--verify", ref)
    except GitCommandError as exc:
        raise SystemExit(f"git_ref_not_found: {ref}") from exc


def current_branch(path: str | Path) -> str | None:
    result = run_git(path, ("symbolic-ref", "--quiet", "--short", "HEAD"), check=False)
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def status_porcelain(path: str | Path) -> list[str]:
    output = git_output(path, "status", "--porcelain=v1", "--untracked-files=all")
    return output.splitlines() if output else []


def porcelain_status_path(line: str) -> str:
    value = line[3:] if len(line) >= 4 else line
    if " -> " in value:
        value = value.split(" -> ", 1)[1]
    return value.strip().strip('"').replace("\\", "/")


def is_clean_except(path: str | Path, allowed_relative_paths: Iterable[str] = ()) -> bool:
    allowed = {value.replace("\\", "/") for value in allowed_relative_paths}
    return all(porcelain_status_path(line) in allowed for line in status_porcelain(path))


def is_clean(path: str | Path) -> bool:
    return is_clean_except(path)


def is_ancestor(repo: str | Path, ancestor: str, descendant: str) -> bool:
    return run_git(repo, ("merge-base", "--is-ancestor", ancestor, descendant), check=False).returncode == 0


def local_and_remote_ref_names(repo: str | Path) -> list[str]:
    output = git_output(
        repo,
        "for-each-ref",
        "--format=%(refname:short)",
        "refs/heads",
        "refs/remotes",
    )
    return [line.strip() for line in output.splitlines() if line.strip()]


def parse_worktree_porcelain(text: str) -> list[WorktreeRecord]:
    records: list[WorktreeRecord] = []
    row: dict[str, Any] = {}

    def flush() -> None:
        nonlocal row
        if not row.get("worktree"):
            row = {}
            return
        records.append(
            WorktreeRecord(
                path=canonical_path(row["worktree"]),
                head=row.get("HEAD"),
                branch=row.get("branch"),
                detached=bool(row.get("detached")),
                bare=bool(row.get("bare")),
                prunable=row.get("prunable"),
            )
        )
        row = {}

    for raw_line in text.splitlines():
        line = raw_line.rstrip("\r\n")
        if not line:
            flush()
            continue
        if " " in line:
            key, value = line.split(" ", 1)
            row[key] = value
        else:
            row[line] = True
    flush()
    return records


def list_worktrees(repo: str | Path) -> list[WorktreeRecord]:
    return parse_worktree_porcelain(git_output(repo, "worktree", "list", "--porcelain"))


def record_for_path(records: Iterable[WorktreeRecord], path: str | Path) -> WorktreeRecord | None:
    expected = path_key(path)
    return next((record for record in records if path_key(record.path) == expected), None)


def records_for_branch(records: Iterable[WorktreeRecord], branch: str) -> list[WorktreeRecord]:
    return [record for record in records if record.branch_short == branch]


def _parse_toml_scalar(value: str) -> Any:
    normalized = value.strip()
    if len(normalized) >= 2 and normalized[0] == normalized[-1] and normalized[0] in {'"', "'"}:
        if normalized[0] == '"':
            try:
                return json.loads(normalized)
            except json.JSONDecodeError as exc:
                raise SystemExit("git_project_config_invalid: invalid quoted string") from exc
        return normalized[1:-1]
    if normalized.lower() == "true":
        return True
    if normalized.lower() == "false":
        return False
    if normalized.startswith("[") and normalized.endswith("]"):
        inner = normalized[1:-1].strip()
        if not inner:
            return []
        parts: list[str] = []
        current = ""
        quote: str | None = None
        for char in inner:
            if char in {'"', "'"}:
                quote = None if quote == char else char if quote is None else quote
                current += char
            elif char == "," and quote is None:
                parts.append(current.strip())
                current = ""
            else:
                current += char
        if current.strip():
            parts.append(current.strip())
        return [_parse_toml_scalar(part) for part in parts]
    return normalized


def load_toml_subset(path: Path) -> dict[str, Any]:
    try:
        import tomllib  # type: ignore[attr-defined]
    except ImportError:  # pragma: no cover - Python 3.10 compatibility
        tomllib = None
    if tomllib is not None:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
        return dict(data)

    data: dict[str, Any] = {}
    current: dict[str, Any] = data
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip()
            if not section or "." in section:
                raise SystemExit(f"git_project_config_invalid: unsupported section {line}")
            current = data.setdefault(section, {})
            if not isinstance(current, dict):
                raise SystemExit(f"git_project_config_invalid: duplicate section {section}")
            continue
        if "=" not in line:
            raise SystemExit(f"git_project_config_invalid: unsupported line {raw_line}")
        key, value = (part.strip() for part in line.split("=", 1))
        current[key] = _parse_toml_scalar(value)
    return data


def _resolve_config_path(value: Any, *, base: Path, fallback: Path) -> Path:
    if not isinstance(value, str) or not value.strip():
        return fallback
    candidate = Path(value.strip()).expanduser()
    if not candidate.is_absolute():
        candidate = base / candidate
    return canonical_path(candidate)


def _string_tuple_config(value: Any, *, name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise SystemExit(f"git_project_config_invalid: {name} must be an array of strings")
    return tuple(item.strip().replace("\\", "/") for item in value)


def _choose_primary_branch(primary_checkout: Path, configured: Any) -> str:
    if isinstance(configured, str) and configured.strip():
        branch = configured.strip()
        if not branch_exists(primary_checkout, branch):
            raise SystemExit(f"primary_branch_missing: {branch}")
        return branch
    for candidate in ("main", "master"):
        if branch_exists(primary_checkout, candidate):
            return candidate
    branch = current_branch(primary_checkout)
    if branch:
        return branch
    raise SystemExit("primary_branch_missing: configure [git].primary_branch")


def load_git_project_config(project_root: Path, repo_root: Path, common_dir: Path) -> GitProjectConfig:
    config_path = project_root / ".acf" / "project.toml"
    raw: dict[str, Any] = {}
    if config_path.is_file():
        parsed = load_toml_subset(config_path)
        section = parsed.get("git", {})
        if not isinstance(section, dict):
            raise SystemExit("git_project_config_invalid: [git] must be a table")
        raw = dict(section)

    default_primary = common_dir.parent if common_dir.name == ".git" else repo_root
    primary_checkout = _resolve_config_path(
        raw.get("primary_checkout"), base=project_root, fallback=canonical_path(default_primary)
    )
    if not primary_checkout.is_dir():
        raise SystemExit(f"primary_checkout_missing: {primary_checkout}")
    expected_common = git_common_dir(primary_checkout)
    if path_key(expected_common) != path_key(common_dir):
        raise SystemExit(
            f"git_common_dir_mismatch: configured primary {primary_checkout} uses {expected_common}, expected {common_dir}"
        )
    primary_branch = _choose_primary_branch(primary_checkout, raw.get("primary_branch"))
    default_root = primary_checkout.parent / f"{primary_checkout.name}_worktrees"
    worktree_root = _resolve_config_path(raw.get("worktree_root"), base=project_root, fallback=default_root)
    branch_prefix = str(raw.get("branch_prefix") or "codex").strip().strip("/")
    if not SLUG_RE.fullmatch(branch_prefix.replace("/", "-")):
        raise SystemExit(f"git_project_config_invalid: invalid branch_prefix {branch_prefix!r}")
    sync_strategy = str(raw.get("sync_strategy") or "merge").strip()
    merge_strategy = str(raw.get("merge_strategy") or "no-ff").strip()
    if sync_strategy != "merge":
        raise SystemExit("git_project_config_invalid: only sync_strategy=merge is supported")
    if merge_strategy != "no-ff":
        raise SystemExit("git_project_config_invalid: only merge_strategy=no-ff is supported")
    primary_dirty_policy = str(
        raw.get("primary_dirty_policy") or "allow_non_overlapping"
    ).strip()
    if primary_dirty_policy not in {"allow_non_overlapping", "require_clean"}:
        raise SystemExit(
            "git_project_config_invalid: primary_dirty_policy must be allow_non_overlapping or require_clean"
        )
    artifact_cache_patterns = _string_tuple_config(
        raw.get("artifact_cache_patterns"),
        name="artifact_cache_patterns",
    )
    artifact_discardable_patterns = _string_tuple_config(
        raw.get("artifact_discardable_patterns"),
        name="artifact_discardable_patterns",
    )
    return GitProjectConfig(
        primary_checkout=primary_checkout,
        primary_branch=primary_branch,
        worktree_root=worktree_root,
        branch_prefix=branch_prefix,
        workstream_branch_template=str(
            raw.get("workstream_branch_template") or "{branch_prefix}/{workstream_lower}-{slug}"
        ),
        workstream_worktree_template=str(
            raw.get("workstream_worktree_template") or "{worktree_root}/{workstream_lower}-{slug}"
        ),
        non_workstream_branch_template=str(
            raw.get("non_workstream_branch_template") or "{branch_prefix}/{kind}-{slug}"
        ),
        non_workstream_worktree_template=str(
            raw.get("non_workstream_worktree_template") or "{worktree_root}/{kind}-{slug}"
        ),
        sync_strategy=sync_strategy,
        merge_strategy=merge_strategy,
        primary_dirty_policy=primary_dirty_policy,
        artifact_cache_patterns=artifact_cache_patterns,
        artifact_discardable_patterns=artifact_discardable_patterns,
        config_path=config_path if config_path.is_file() else None,
    )


def discover_git_project(path: str | Path | None = None) -> GitProject:
    location = discover_context(Path(path) if path is not None else None)
    context_root = location.context_root
    project_root = infer_project_root(context_root).resolve()
    repo_root = git_toplevel(project_root)
    common_dir = git_common_dir(repo_root)
    config = load_git_project_config(project_root, repo_root, common_dir)
    return GitProject(
        context_root=context_root,
        project_root=project_root,
        repo_root=repo_root,
        common_dir=common_dir,
        config=config,
    )


def validate_slug(value: str, *, allow_low_information: bool = False) -> str:
    slug = value.strip().lower()
    if not SLUG_RE.fullmatch(slug):
        raise SystemExit(
            "worktree_slug_invalid: use lowercase ASCII letters, digits, and single hyphens"
        )
    if slug in LOW_INFORMATION_SLUGS and not allow_low_information:
        raise SystemExit(f"invalid_low_information_slug: {slug}")
    return slug


def render_template(template: str, values: Mapping[str, str]) -> str:
    try:
        rendered = template.format(**values)
    except (KeyError, ValueError) as exc:
        raise SystemExit(f"git_project_config_invalid: invalid naming template {template!r}") from exc
    if not rendered.strip():
        raise SystemExit("git_project_config_invalid: naming template rendered empty")
    return rendered


def build_workstream_target(
    project: GitProject,
    *,
    workstream_id: str,
    slug: str,
    base_commit: str,
    reservation_path: str,
    reservation_commit: str,
) -> WorktreeTarget:
    normalized_id = workstream_id.upper()
    slug = validate_slug(slug)
    values = {
        "branch_prefix": project.config.branch_prefix,
        "workstream": normalized_id,
        "workstream_lower": normalized_id.lower(),
        "slug": slug,
        "worktree_root": project.config.worktree_root.as_posix(),
        "kind": "",
    }
    branch = render_template(project.config.workstream_branch_template, values).replace("\\", "/")
    path = canonical_path(render_template(project.config.workstream_worktree_template, values))
    return WorktreeTarget(
        key=normalized_id,
        branch=branch,
        path=path,
        base_branch=project.config.primary_branch,
        base_commit=base_commit,
        workstream_id=normalized_id,
        slug=slug,
        reservation_path=reservation_path,
        reservation_commit=reservation_commit,
    )


def build_non_workstream_target(
    project: GitProject, *, kind: str, slug: str, base_commit: str
) -> WorktreeTarget:
    if kind not in ALLOWED_NON_WORKSTREAM_KINDS:
        raise SystemExit(
            f"worktree_kind_invalid: choose one of {', '.join(ALLOWED_NON_WORKSTREAM_KINDS)}"
        )
    slug = validate_slug(slug)
    values = {
        "branch_prefix": project.config.branch_prefix,
        "workstream": "",
        "workstream_lower": "",
        "slug": slug,
        "worktree_root": project.config.worktree_root.as_posix(),
        "kind": kind,
    }
    branch = render_template(project.config.non_workstream_branch_template, values).replace("\\", "/")
    path = canonical_path(render_template(project.config.non_workstream_worktree_template, values))
    return WorktreeTarget(
        key=f"{kind}:{slug}",
        branch=branch,
        path=path,
        base_branch=project.config.primary_branch,
        base_commit=base_commit,
        kind=kind,
        slug=slug,
    )


def acf_git_state_root(common_dir: Path) -> Path:
    return common_dir / "acf"


def operations_dir(common_dir: Path) -> Path:
    return acf_git_state_root(common_dir) / "operations"


def registry_dir(common_dir: Path) -> Path:
    return acf_git_state_root(common_dir) / "worktrees"


def locks_dir(common_dir: Path) -> Path:
    return acf_git_state_root(common_dir) / "locks"


def safe_file_key(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip(".-")
    return normalized or "operation"


def operation_path(common_dir: Path, operation_id: str) -> Path:
    return operations_dir(common_dir) / f"{safe_file_key(operation_id)}.json"


def registry_path(common_dir: Path, key: str) -> Path:
    return registry_dir(common_dir) / f"{safe_file_key(key)}.json"


def lock_path(common_dir: Path, key: str) -> Path:
    return locks_dir(common_dir) / f"{safe_file_key(key)}.lock"


def atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def read_json_object(path: Path, *, error_code: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"{error_code}: {path}") from exc
    if not isinstance(payload, dict):
        raise SystemExit(f"{error_code}: {path}")
    return payload


def acquire_operation_lock(common_dir: Path, key: str, operation_id: str) -> Path:
    path = lock_path(common_dir, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "acf.git_lock.v1",
        "operation_id": operation_id,
        "pid": os.getpid(),
        "hostname": socket.gethostname(),
        "created_at": utc_now(),
    }
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    try:
        descriptor = os.open(path, flags)
    except FileExistsError as exc:
        existing = read_json_object(path, error_code="worktree_lock_invalid")
        raise SystemExit(
            f"worktree_operation_locked: {key} held by {existing.get('operation_id', 'unknown')}"
        ) from exc
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    return path


def release_operation_lock(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        return


def new_operation_id(prefix: str) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"{safe_file_key(prefix)}-{timestamp}-{os.getpid()}"


def create_operation(
    common_dir: Path,
    *,
    command: str,
    target: WorktreeTarget | None,
    extra: Mapping[str, Any] | None = None,
    operation_id: str | None = None,
) -> dict[str, Any]:
    op_id = operation_id or new_operation_id(command)
    payload: dict[str, Any] = {
        "schema_version": "acf.git_operation.v1",
        "operation_id": op_id,
        "command": command,
        "status": "planned",
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "steps": {},
        "resume_allowed": True,
    }
    if target is not None:
        payload["target"] = {
            **asdict(target),
            "path": str(target.path),
        }
    if extra:
        payload.update(dict(extra))
    atomic_write_json(operation_path(common_dir, op_id), payload)
    return payload


def update_operation(common_dir: Path, payload: dict[str, Any], **updates: Any) -> dict[str, Any]:
    payload.update(updates)
    payload["updated_at"] = utc_now()
    atomic_write_json(operation_path(common_dir, str(payload["operation_id"])), payload)
    return payload


def update_operation_step(
    common_dir: Path,
    payload: dict[str, Any],
    step: str,
    state: str,
    **details: Any,
) -> dict[str, Any]:
    steps = payload.setdefault("steps", {})
    if not isinstance(steps, dict):
        raise SystemExit("operation_journal_invalid: steps is not an object")
    row: dict[str, Any] = {"state": state, "updated_at": utc_now()}
    row.update(details)
    steps[step] = row
    return update_operation(common_dir, payload)


def load_operation(common_dir: Path, operation_id: str) -> dict[str, Any]:
    path = operation_path(common_dir, operation_id)
    if not path.is_file():
        raise SystemExit(f"operation_not_found: {operation_id}")
    return read_json_object(path, error_code="operation_journal_invalid")


def write_registry(common_dir: Path, key: str, payload: Mapping[str, Any]) -> Path:
    path = registry_path(common_dir, key)
    row = {
        "schema_version": "acf.worktree_registry.v1",
        "key": key,
        "updated_at": utc_now(),
        **dict(payload),
    }
    atomic_write_json(path, row)
    return path


def read_registry(common_dir: Path, key: str) -> dict[str, Any] | None:
    path = registry_path(common_dir, key)
    if not path.is_file():
        return None
    return read_json_object(path, error_code="worktree_registry_invalid")


def list_registries(common_dir: Path) -> list[dict[str, Any]]:
    directory = registry_dir(common_dir)
    if not directory.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.json")):
        row = read_json_object(path, error_code="worktree_registry_invalid")
        row["registry_path"] = str(path)
        rows.append(row)
    return rows


def delete_registry(common_dir: Path, key: str) -> None:
    try:
        registry_path(common_dir, key).unlink()
    except FileNotFoundError:
        return


def workstream_numbers_from_text(text: str) -> set[int]:
    return {int(match.group(1)) for match in WORKSTREAM_TOKEN_RE.finditer(text)}


def scan_used_workstream_numbers(project: GitProject) -> dict[int, list[str]]:
    evidence: dict[int, list[str]] = {}

    def add(number: int, source: str) -> None:
        evidence.setdefault(number, []).append(source)

    for directory in (
        project.context_root / "active" / "workstreams",
        project.context_root / "archive" / "workstreams",
    ):
        if directory.is_dir():
            for path in directory.glob("WS*.md"):
                for number in workstream_numbers_from_text(path.stem):
                    add(number, str(path))
    index_path = project.context_root / "active" / "Workstreams.md"
    if index_path.is_file():
        for number in workstream_numbers_from_text(index_path.read_text(encoding="utf-8")):
            add(number, str(index_path))
    for ref in local_and_remote_ref_names(project.repo_root):
        for number in workstream_numbers_from_text(ref):
            add(number, f"git-ref:{ref}")
    for record in list_worktrees(project.repo_root):
        values = [str(record.path), record.branch_short or ""]
        for value in values:
            for number in workstream_numbers_from_text(value):
                add(number, f"worktree:{record.path}")
    for row in list_registries(project.common_dir):
        for number in workstream_numbers_from_text(json.dumps(row, ensure_ascii=False)):
            add(number, f"registry:{row.get('registry_path')}")
    operation_root = operations_dir(project.common_dir)
    if operation_root.is_dir():
        for path in operation_root.glob("*.json"):
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            for number in workstream_numbers_from_text(text):
                add(number, f"operation:{path}")
    return evidence


def next_workstream_id(project: GitProject) -> tuple[str, dict[int, list[str]]]:
    evidence = scan_used_workstream_numbers(project)
    number = max(evidence, default=0) + 1
    while number in evidence:
        number += 1
    return f"WS{number:03d}", evidence


def git_path_in_ref_exists(repo: Path, ref: str, relative_path: str) -> bool:
    result = run_git(repo, ("cat-file", "-e", f"{ref}:{relative_path}"), check=False)
    return result.returncode == 0


def commit_for_path(repo: Path, ref: str, relative_path: str) -> str | None:
    result = run_git(
        repo,
        ("log", "-1", "--format=%H", ref, "--", relative_path),
        check=False,
    )
    value = result.stdout.strip()
    return value or None


def staged_paths(repo: Path) -> list[str]:
    output = git_output(repo, "diff", "--cached", "--name-only", "--diff-filter=ACMR")
    return [line.strip().replace("\\", "/") for line in output.splitlines() if line.strip()]


def merge_tree(repo: Path, target_ref: str, source_ref: str) -> dict[str, Any]:
    modern = run_git(repo, ("merge-tree", "--write-tree", target_ref, source_ref), check=False)
    if modern.returncode in {0, 1}:
        return {
            "ok": modern.returncode == 0,
            "returncode": modern.returncode,
            "stdout": modern.stdout,
            "stderr": modern.stderr,
            "tree": modern.stdout.strip().splitlines()[0] if modern.returncode == 0 and modern.stdout.strip() else None,
            "mode": "write-tree",
        }
    base_result = run_git(repo, ("merge-base", target_ref, source_ref), check=False)
    if base_result.returncode != 0:
        return {
            "ok": False,
            "returncode": base_result.returncode,
            "stdout": base_result.stdout,
            "stderr": base_result.stderr,
            "tree": None,
            "mode": "merge-base-failed",
        }
    base = base_result.stdout.strip()
    legacy = run_git(repo, ("merge-tree", base, target_ref, source_ref), check=False)
    text = legacy.stdout + legacy.stderr
    conflict = "<<<<<<<" in text or "changed in both" in text or "CONFLICT" in text
    return {
        "ok": legacy.returncode == 0 and not conflict,
        "returncode": legacy.returncode,
        "stdout": legacy.stdout,
        "stderr": legacy.stderr,
        "tree": None,
        "mode": "legacy",
    }


def target_payload(target: WorktreeTarget) -> dict[str, Any]:
    return {
        **asdict(target),
        "path": str(target.path),
    }
