#!/usr/bin/env python3
"""Exercise the installed ACF console script through a full worktree lifecycle.

The script creates a disposable Git repository, reserves a Workstream, creates
and verifies its optional linked worktree, commits a feature, marks the
Workstream ReadyToMerge, performs a no-ff merge, and safely closes the worktree.
It is intended for wheel and production ``uv tool`` smoke tests.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Sequence


class SmokeFailure(RuntimeError):
    pass


def run(
    argv: Sequence[str],
    *,
    cwd: Path,
    expect: int = 0,
    json_output: bool = False,
) -> dict[str, Any] | subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        list(argv),
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
        check=False,
    )
    if completed.returncode != expect:
        raise SmokeFailure(
            f"command failed ({completed.returncode} != {expect}): {list(argv)!r}\n"
            f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )
    if not json_output:
        return completed
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise SmokeFailure(
            f"command did not return JSON: {list(argv)!r}\n{completed.stdout}"
        ) from exc
    if not isinstance(payload, dict):
        raise SmokeFailure(f"JSON payload is not an object: {list(argv)!r}")
    return payload


def git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    result = run(["git", *args], cwd=repo)
    assert isinstance(result, subprocess.CompletedProcess)
    return result


def acf_json(acf_prefix: Sequence[str], cwd: Path, *args: str) -> dict[str, Any]:
    payload = run([*acf_prefix, *args, "--json"], cwd=cwd, json_output=True)
    assert isinstance(payload, dict)
    if payload.get("ok") is not True:
        raise SmokeFailure(f"ACF reported failure: {payload}")
    return payload


def lifecycle(acf_prefix: Sequence[str], root: Path) -> dict[str, Any]:
    repo = root / "project"
    repo.mkdir(parents=True)
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.name", "ACF Release Smoke")
    git(repo, "config", "user.email", "acf-release-smoke@example.invalid")

    context = repo / "docs" / "ai"
    acf_json(acf_prefix, repo, "init", str(context), "--profile", "standard")
    acf_json(acf_prefix, repo, "workstream", "init", str(context))
    git(repo, "add", "--all")
    git(repo, "commit", "-m", "initial context")

    reserved = acf_json(
        acf_prefix,
        repo,
        "workstream",
        "reserve",
        str(context),
        "--title",
        "Installed worktree lifecycle smoke",
        "--slug",
        "installed-lifecycle-smoke",
        "--owner",
        "release-smoke",
        "--goal",
        "Verify the installed ACF console script.",
        "--output",
        "A completed disposable worktree lifecycle.",
        "--apply",
    )
    workstream_id = str(reserved["id"])
    if workstream_id != "WS001":
        raise SmokeFailure(f"unexpected reserved id: {workstream_id}")

    created = acf_json(
        acf_prefix,
        repo,
        "worktree",
        "create",
        str(context),
        "--workstream",
        workstream_id,
        "--apply",
    )
    target = Path(str(created["target"]["path"]))
    if not target.is_dir():
        raise SmokeFailure(f"worktree was not created: {target}")

    verified = acf_json(
        acf_prefix,
        repo,
        "worktree",
        "verify",
        str(context),
        "--workstream",
        workstream_id,
    )
    if verified.get("branch") != "codex/ws001-installed-lifecycle-smoke":
        raise SmokeFailure(f"unexpected branch: {verified.get('branch')}")

    (target / "feature.txt").write_text("installed lifecycle smoke\n", encoding="utf-8")
    git(target, "add", "feature.txt")
    git(target, "commit", "-m", "add installed lifecycle feature")

    target_context = target / "docs" / "ai"
    acf_json(
        acf_prefix,
        target,
        "workstream",
        "set",
        workstream_id,
        str(target_context),
        "--status",
        "Active",
    )
    worktree_status = acf_json(
        acf_prefix,
        target,
        "status",
        str(target_context),
    )
    if worktree_status.get("workstream_state") != "WorktreeSelected":
        raise SmokeFailure(f"verified worktree was not selected: {worktree_status}")
    if worktree_status.get("selected_workstream") != workstream_id:
        raise SmokeFailure(f"unexpected selected workstream: {worktree_status}")
    if worktree_status.get("disclosure_level") != "workstream_pointer":
        raise SmokeFailure(f"worktree status was not pointer-only: {worktree_status}")
    acf_json(
        acf_prefix,
        target,
        "workstream",
        "merge-request",
        workstream_id,
        str(target_context),
        "--target",
        "main",
        "--summary",
        "Merge installed lifecycle smoke.",
        "--verification",
        "Installed CLI create and verify passed.",
    )
    acf_json(
        acf_prefix,
        target,
        "workstream",
        "ready",
        workstream_id,
        str(target_context),
        "--human-approved",
    )
    git(target, "add", "--all")
    git(target, "commit", "-m", "mark installed lifecycle ready")

    pre_check = json.dumps(["git", "status", "--porcelain"])
    post_check = json.dumps(
        ["git", "merge-base", "--is-ancestor", "HEAD^2", "HEAD"]
    )
    merged = acf_json(
        acf_prefix,
        repo,
        "worktree",
        "merge",
        str(context),
        "--workstream",
        workstream_id,
        "--pre-check-json",
        pre_check,
        "--post-check-json",
        post_check,
        "--apply",
    )
    if merged.get("status") != "merged":
        raise SmokeFailure(f"unexpected merge status: {merged}")
    parents = git(repo, "show", "-s", "--format=%P", "HEAD").stdout.split()
    if len(parents) != 2:
        raise SmokeFailure(f"expected a no-ff merge commit, got parents={parents}")
    if not (repo / "feature.txt").is_file():
        raise SmokeFailure("merged feature is missing from primary checkout")

    global_status = acf_json(acf_prefix, repo, "status", str(context))
    if global_status.get("workstream_state") != "GlobalOnly":
        raise SmokeFailure(f"primary checkout did not remain global-only: {global_status}")
    if global_status.get("selected_workstream") is not None:
        raise SmokeFailure(f"primary checkout selected a Workstream implicitly: {global_status}")
    explicit_status = acf_json(
        acf_prefix,
        repo,
        "status",
        str(context),
        "--workstream",
        workstream_id,
    )
    if explicit_status.get("workstream_state") != "Selected":
        raise SmokeFailure(f"explicit selection failed: {explicit_status}")
    if explicit_status.get("disclosure_level") != "workstream_pointer":
        raise SmokeFailure(f"explicit selection was not pointer-only: {explicit_status}")

    closed = acf_json(
        acf_prefix,
        repo,
        "worktree",
        "close",
        str(context),
        "--workstream",
        workstream_id,
        "--apply",
    )
    if closed.get("status") != "closed":
        raise SmokeFailure(f"unexpected close status: {closed}")
    if target.exists():
        raise SmokeFailure(f"worktree path still exists after close: {target}")
    branch_list = git(
        repo, "branch", "--list", "codex/ws001-installed-lifecycle-smoke"
    ).stdout.strip()
    if branch_list:
        raise SmokeFailure(f"feature branch still exists after close: {branch_list}")

    audit = acf_json(acf_prefix, repo, "worktree", "audit", str(context))
    return {
        "schema_version": 1,
        "ok": True,
        "workstream_id": workstream_id,
        "reservation_commit": reserved.get("reservation_commit"),
        "merge_commit": merged.get("merge_commit"),
        "worktree_closed": True,
        "global_state": global_status.get("workstream_state"),
        "worktree_state": worktree_status.get("workstream_state"),
        "explicit_state": explicit_status.get("workstream_state"),
        "audit_findings": audit.get("findings", []),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--acf",
        nargs="+",
        default=["acf"],
        help="ACF command prefix, for example: --acf uv run acf",
    )
    parser.add_argument("--keep-tmp", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    temp = Path(tempfile.mkdtemp(prefix="acf-worktree-release-smoke-"))
    try:
        result = lifecycle(args.acf, temp)
        if args.keep_tmp:
            result["temp_root"] = str(temp)
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        print(
            json.dumps(
                {
                    "schema_version": 1,
                    "ok": False,
                    "error": f"{type(exc).__name__}: {exc}",
                    "temp_root": str(temp),
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    finally:
        if not args.keep_tmp:
            shutil.rmtree(temp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
