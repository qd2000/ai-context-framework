"""Run the release gates and verify wheel/sdist installation paths.

The package smoke checks intentionally install artifacts in isolated uv
environments and redirect ACF_HOME and uv's tool/cache directories to a
temporary directory. This keeps release validation away from the developer's
global ACF logs and installed tools. Repository strict checks run separately
before the artifact smoke.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from contextlib import nullcontext
from pathlib import Path
from typing import Any, Iterator


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_PREFIX = "ai_context_framework-"


class ReleaseCheckError(RuntimeError):
    pass


def run_command(
    command: list[str],
    *,
    cwd: Path = ROOT,
    env: dict[str, str] | None = None,
    label: str,
) -> subprocess.CompletedProcess[str]:
    print(f"[release-check] {label}: {' '.join(command)}")
    completed = subprocess.run(
        command,
        cwd=str(cwd),
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        detail = "\n".join(
            part.strip() for part in (completed.stdout, completed.stderr) if part.strip()
        )
        if len(detail) > 4000:
            detail = detail[-4000:]
        raise ReleaseCheckError(
            f"{label} failed with exit code {completed.returncode}\n{detail}"
        )
    return completed


def release_environment(root: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["ACF_HOME"] = str(root / "acf-home")
    env["UV_CACHE_DIR"] = str(root / "uv-cache")
    env["UV_TOOL_DIR"] = str(root / "uv-tools")
    env["UV_TOOL_BIN_DIR"] = str(root / "uv-bin")
    return env


def project_version() -> str:
    version_path = ROOT / "ai_context_framework" / "version.py"
    pyproject_path = ROOT / "pyproject.toml"
    cli_match = re.search(r'^VERSION = "([^"]+)"$', version_path.read_text(encoding="utf-8"), re.MULTILINE)
    package_match = re.search(r'^version = "([^"]+)"$', pyproject_path.read_text(encoding="utf-8"), re.MULTILINE)
    if cli_match is None or package_match is None:
        raise ReleaseCheckError("could not read project version from version.py and pyproject.toml")
    cli_version = cli_match.group(1)
    package_version = package_match.group(1)
    if cli_version.removeprefix("v") != package_version:
        raise ReleaseCheckError(
            f"CLI/package version mismatch: cli={cli_version}, package={package_version}"
        )
    return cli_version


def verify_release_tag() -> None:
    tag = os.environ.get("GITHUB_REF_NAME", "")
    if not tag.startswith("v"):
        return
    version = project_version()
    if tag != version:
        raise ReleaseCheckError(f"GitHub tag {tag} does not match project version {version}")


def artifact_files(dist_dir: Path) -> tuple[Path, Path]:
    wheels = sorted(dist_dir.glob(f"{PACKAGE_PREFIX}*.whl"))
    sdists = sorted(dist_dir.glob(f"{PACKAGE_PREFIX}*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        raise ReleaseCheckError(
            "expected exactly one wheel and one sdist in "
            f"{dist_dir}, found wheels={len(wheels)}, sdists={len(sdists)}"
        )
    return wheels[0], sdists[0]


def run_repository_gates(args: argparse.Namespace) -> None:
    gates: list[tuple[str, list[str]]] = [
        ("template check", ["uv", "run", "acf", "check", "template"]),
        ("strict check", ["uv", "run", "acf", "check", "--strict"]),
        (
            "minimal smoke",
            [
                "uv",
                "run",
                "python",
                "scripts/minimal_smoke.py",
                "--acf",
                "uv",
                "run",
                "acf",
            ],
        ),
    ]
    if not args.skip_tests:
        gates.append(("unit tests", ["uv", "run", "python", "-m", "unittest"]))
    if not args.skip_upgrade_matrix:
        gates.append(
            (
                "full upgrade matrix",
                [
                    "uv",
                    "run",
                    "python",
                    "scripts/upgrade_matrix.py",
                    "--mode",
                    "full",
                    "--acf",
                    "uv",
                    "run",
                    "acf",
                ],
            )
        )
    for label, command in gates:
        run_command(command, label=label)


def package_smoke(artifact: Path, root: Path, *, label: str) -> dict[str, Any]:
    artifact = artifact.resolve()
    project = root / f"project-{label}"
    context = project / "docs" / "ai"
    project.mkdir(parents=True)
    tool_root = root / f"tool-{label}"
    tool_env = release_environment(tool_root)
    run_command(
        ["uv", "tool", "install", str(artifact)],
        cwd=project,
        env=tool_env,
        label=f"{label} uv tool install",
    )
    executable_name = "acf.exe" if os.name == "nt" else "acf"
    executable = tool_root / "uv-bin" / executable_name
    if not executable.exists():
        raise ReleaseCheckError(f"installed console script is missing: {executable}")
    version = run_command(
        [str(executable), "--version"],
        cwd=project,
        env=tool_env,
        label=f"{label} installed acf --version",
    )
    run_command(
        [
            str(executable),
            "init",
            str(context),
            "--profile",
            "minimal",
            "--json",
        ],
        cwd=project,
        env=tool_env,
        label=f"{label} installed acf init",
    )
    run_command(
        [
            str(executable),
            "check",
            str(context),
            "--json",
        ],
        cwd=project,
        env=tool_env,
        label=f"{label} installed acf check",
    )
    observer_status = run_command(
        [str(executable), "observer", "status", str(project), "--json"],
        cwd=project,
        env=tool_env,
        label=f"{label} installed acf observer status",
    )
    observer_snapshot = run_command(
        [str(executable), "observer", "snapshot", str(project), "--json"],
        cwd=project,
        env=tool_env,
        label=f"{label} installed acf observer snapshot",
    )
    try:
        observer_payload = json.loads(observer_snapshot.stdout)
    except json.JSONDecodeError as exc:
        raise ReleaseCheckError(f"{label} installed Observer snapshot did not return JSON") from exc
    observer_dir = Path(str(observer_payload.get("observer_dir") or ""))
    dashboard = observer_dir / "dashboard.html"
    if not observer_dir.is_dir() or not dashboard.is_file():
        raise ReleaseCheckError(
            f"{label} installed Observer did not create its user-level dashboard: {dashboard}"
        )
    return {
        "artifact": str(artifact),
        "version_output": version.stdout.strip(),
        "context": str(context),
        "observer_status_ok": bool(json.loads(observer_status.stdout).get("ok")),
        "observer_snapshot_ok": bool(observer_payload.get("ok")),
        "observer_dashboard": str(dashboard),
    }


def dist_context(output_dir: Path | None) -> Iterator[Path]:
    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        return nullcontext(output_dir)  # type: ignore[return-value]
    return tempfile.TemporaryDirectory(prefix="acf-release-dist-")  # type: ignore[return-value]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run ACF release gates and artifact smoke tests.")
    parser.add_argument(
        "--mode",
        choices=("full", "package"),
        default="full",
        help="full runs repository gates; package only validates built artifacts",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="keep build artifacts in this directory; defaults to a temporary directory",
    )
    parser.add_argument("--skip-tests", action="store_true", help="skip the full unittest suite")
    parser.add_argument("--skip-upgrade-matrix", action="store_true", help="skip the full upgrade matrix")
    args = parser.parse_args(argv)

    if shutil.which("uv") is None:
        raise ReleaseCheckError("uv was not found on PATH")
    version = project_version()
    verify_release_tag()
    if args.mode == "full":
        run_repository_gates(args)

    with dist_context(args.output_dir) as dist_path:
        dist_dir = Path(dist_path)
        run_command(
            ["uv", "build", "--no-sources", "--out-dir", str(dist_dir)],
            label="build wheel and sdist",
        )
        wheel, sdist = artifact_files(dist_dir)
        with tempfile.TemporaryDirectory(prefix="acf-release-smoke-") as smoke_tmp:
            smoke_root = Path(smoke_tmp)
            results = [
                package_smoke(wheel, smoke_root, label="wheel"),
                package_smoke(sdist, smoke_root, label="sdist"),
            ]

    payload = {
        "schema_version": 1,
        "command": "release_check",
        "ok": True,
        "mode": args.mode,
        "version": version,
        "artifacts": [str(wheel), str(sdist)],
        "package_smoke": results,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ReleaseCheckError as exc:
        print(f"release-check failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
