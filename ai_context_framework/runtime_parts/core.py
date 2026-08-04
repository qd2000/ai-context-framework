"""Legacy runtime functions split out for agent-friendly navigation.

Names in this module are rebound by ai_context_framework.runtime so the
migration can stay mechanical while behavior remains unchanged.
"""

from __future__ import annotations
import re

def write_command_context_root(args: argparse.Namespace) -> Path | None:
    command = getattr(args, "command", None)
    if command in {"init", "simplify"}:
        return None
    if command == "doctor":
        doctor_writes = (
            getattr(args, "fix", "none") != "none"
            or bool(getattr(args, "report", False))
            or bool(getattr(args, "draft_semantic", False))
        )
        if doctor_writes and not getattr(args, "projects", None):
            return require_context_root(getattr(args, "path", None))
        return None
    if command == "workstream":
        if getattr(args, "workstream_command", None) == "stage":
            if getattr(args, "workstream_stage_command", None) in {"add", "done"}:
                return require_context_root(getattr(args, "path", None))
            return None
        if getattr(args, "workstream_command", None) == "reserve":
            return require_context_root(getattr(args, "path", None)) if getattr(args, "apply", False) else None
        if getattr(args, "workstream_command", None) in {
            "init",
            "add",
            "set",
            "sync",
            "block",
            "cancel",
            "merge-request",
            "merge-start",
            "ready",
            "done",
            "archive-draft",
            "archive",
            "focus",
            "claim",
            "scope-add",
            "note",
        }:
            return require_context_root(getattr(args, "path", None))
        return None
    if command == "upgrade" and getattr(args, "plan", False):
        return None
    if command in {"upgrade", "new", "writeback", "plan", "task", "archive", "decisions", "knowledge", "curate", "linkify"}:
        return require_context_root(getattr(args, "path", None))
    if command == "human":
        if getattr(args, "human_command", None) == "mark":
            return require_context_root(getattr(args, "path", None))
        if getattr(args, "human_command", None) == "index" and getattr(args, "human_index_command", None) == "sync":
            return require_context_root(getattr(args, "path", None))
        return None
    if command == "link":
        if getattr(args, "link_command", None) == "add":
            return require_context_root(getattr(args, "path", None))
        return None
    if command == "edit":
        return require_context_root(getattr(args, "context", None))
    return None


def run_with_context_lock(args: argparse.Namespace) -> int:
    if dry_run_enabled(args):
        return args.func(args)
    root = write_command_context_root(args)
    if root is None:
        return args.func(args)
    lock_path = acquire_context_lock(root, command_label(args))
    try:
        return args.func(args)
    finally:
        release_context_lock(lock_path)


def maybe_check_after(args: argparse.Namespace, root: Path, profile: str | None = None) -> CheckResult | None:
    if not check_after_enabled(args) or dry_run_enabled(args):
        return None
    return check_context(root, profile or infer_context_profile(root), bool(getattr(args, "strict", False)))


def required_dirs(profile: str) -> tuple[str, ...]:
    return MINIMAL_DIRS if profile == "minimal" else STANDARD_DIRS


def required_files(profile: str) -> tuple[str, ...]:
    return MINIMAL_FILES if profile == "minimal" else STANDARD_FILES


def required_files_for_check(root: Path, profile: str) -> tuple[str, ...]:
    files = required_files(profile)
    if root.resolve() == TEMPLATE_DIR.resolve():
        return files
    return tuple(rel for rel in files if rel not in TEMPLATE_EXAMPLE_FILES)


def human_layer_paths(root: Path) -> list[Path]:
    return [
        root / "human" / "Human_Index.md",
        root / "human" / "Human_Notes.md",
        root / "human" / "weekly" / ".gitkeep",
        root / "human" / "reports" / ".gitkeep",
    ]


def skip_placeholder_check(root: Path, rel_file: str) -> bool:
    return root.resolve() != TEMPLATE_DIR.resolve() and rel_file in TEMPLATE_EXAMPLE_FILES


def ensure_clean_target(target: Path, force: bool, dry_run: bool = False) -> None:
    if not target.exists():
        return
    if force:
        if dry_run:
            return
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
        return
    if target.is_dir() and not any(target.iterdir()):
        return
    raise SystemExit(f"target already exists and is not empty: {target}")


def copy_selected_files(source: Path, target: Path, files: Sequence[str], dirs: Sequence[str]) -> None:
    for dirname in dirs:
        (target / dirname).mkdir(parents=True, exist_ok=True)
    for rel in files:
        src = source / rel
        dst = target / rel
        if not src.exists():
            raise SystemExit(f"template source file is missing: {src}")
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def render_root_agents(project_name: str, context_rel: str) -> str:
    context_rel = context_rel.rstrip("/")
    return f"""# {project_name}

本仓库使用 AI context framework 管理项目上下文。

默认从项目 AI 上下文进入：

1. 先读取 `{context_rel}/AGENTS.md`
2. 再按其中的读取顺序读取当前有效上下文

## 仓库级约定

- 文档内容默认使用中文。
- 文件名和目录名使用英文。
- 不依赖特定 AI 模型或私有上下文格式。
- `{context_rel}/` 是本项目的 AI 上下文目录。
- 不要把上下文目录中的模板占位内容当作当前项目事实。
"""


def write_root_agents(context_root: Path, force: bool) -> Path | None:
    project_root = infer_project_root(context_root)
    root_agents = project_root / "AGENTS.md"
    if root_agents.exists() and root_agents.is_dir():
        raise SystemExit(f"root AGENTS.md path is a directory: {root_agents}")
    if root_agents.exists() and not force:
        return None

    context_rel = relative_display_path(context_root, project_root)
    project_name = project_root.name or "Project"
    root_agents.write_text(render_root_agents(project_name, context_rel), encoding="utf-8")
    return root_agents


def planned_root_agents_path(context_root: Path, force: bool) -> Path | None:
    project_root = infer_project_root(context_root)
    root_agents = project_root / "AGENTS.md"
    if root_agents.exists() and root_agents.is_dir():
        raise SystemExit(f"root AGENTS.md path is a directory: {root_agents}")
    if root_agents.exists() and not force:
        return None
    return root_agents


def planned_init_files(target: Path, profile: str, force_root_agent: bool) -> list[Path]:
    files = STANDARD_FILES if profile == "standard" else MINIMAL_FILES
    changed_files = [target / rel_path for rel_path in files]
    root_agents = planned_root_agents_path(target, force_root_agent)
    if root_agents is not None:
        changed_files.append(root_agents)
    return changed_files


def dynamic_minimal_rel_files(source: Path) -> list[str]:
    rel_files: list[str] = []
    dynamic_groups = (
        ("decisions", "ADR-*.md", {"ADR-0001-template.md"}),
        ("worklog/daily", "*.md", {"YYYY-MM-DD.md"}),
    )
    for dirname, pattern, excluded_names in dynamic_groups:
        src_dir = source / dirname
        if not src_dir.exists():
            continue
        for src in sorted(src_dir.glob(pattern)):
            if not src.is_file() or src.name in excluded_names:
                continue
            rel_files.append(src.relative_to(source).as_posix())
    return rel_files


def planned_simplify_files(source: Path, target: Path) -> list[Path]:
    rel_files = list(MINIMAL_FILES) + dynamic_minimal_rel_files(source)
    return [target / rel_path for rel_path in rel_files]


def copy_dynamic_minimal_files(source: Path, target: Path) -> None:
    for rel_path in dynamic_minimal_rel_files(source):
        src = source / rel_path
        dst = target / rel_path
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def remove_worklog_example_block(text: str) -> str:
    lines = text.splitlines()
    start = next((index for index, line in enumerate(lines) if line.strip() == "填写示例："), None)
    if start is None:
        return text
    end = next(
        (
            index
            for index, line in enumerate(lines[start + 1 :], start=start + 1)
            if line.strip() == "---"
        ),
        len(lines),
    )
    updated = lines[:start] + lines[end:]
    return "\n".join(updated).rstrip() + "\n"


def sanitize_minimal_indexes(target: Path) -> None:
    decisions_index = target / "reference" / "Decisions_Index.md"
    if decisions_index.exists():
        decisions_index.write_text(
            remove_markdown_section(read_text(decisions_index), "## 示例"),
            encoding="utf-8",
        )

    worklog_index = target / "worklog" / "Worklog_Index.md"
    if worklog_index.exists():
        worklog_index.write_text(
            remove_worklog_example_block(read_text(worklog_index)),
            encoding="utf-8",
        )


def write_minimal_overrides(target: Path) -> None:
    (target / "AGENTS.md").write_text(MINIMAL_AGENTS, encoding="utf-8")
    sanitize_minimal_indexes(target)


