"""Run upgrade compatibility fixtures for acf.

The matrix verifies that old-shaped contexts can be brought to a
tool-governable state without destructive edits. Fixtures are intentionally
minimal: each one records the old-version risk it represents, then the runner
materializes that shape in a temporary project before exercising the CLI.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "upgrade_matrix"
DEFAULT_TODAY = "2026-05-05"


def parse_json_output(stdout: str) -> dict[str, Any]:
    text = stdout.strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise


def load_fixture(path: Path) -> dict[str, Any]:
    metadata = json.loads((path / "metadata.json").read_text(encoding="utf-8"))
    metadata["fixture"] = path.name
    metadata["path"] = str(path)
    return metadata


def discover_fixtures(mode: str) -> list[dict[str, Any]]:
    fixtures = [load_fixture(path) for path in sorted(FIXTURE_ROOT.iterdir()) if path.is_dir()]
    if mode == "quick":
        fixtures = [fixture for fixture in fixtures if fixture.get("quick") is True]
    return fixtures


class UpgradeMatrixRunner:
    def __init__(self, acf_cmd: list[str], keep_tmp: bool = False) -> None:
        self.acf_cmd = acf_cmd
        self.keep_tmp = keep_tmp

    def run_acf(
        self,
        args: list[str],
        *,
        cwd: Path | None = None,
        expect_exit: int | tuple[int, ...] = 0,
        expect_error_code: str | None = None,
        env_extra: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        env = os.environ.copy()
        env.setdefault("PYTHONUTF8", "1")
        if env_extra:
            env.update(env_extra)
        completed = subprocess.run(
            [*self.acf_cmd, *args],
            cwd=str(cwd) if cwd is not None else None,
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        payload = parse_json_output(completed.stdout)
        expected_exits = expect_exit if isinstance(expect_exit, tuple) else (expect_exit,)
        ok = completed.returncode in expected_exits
        if expect_error_code is not None:
            ok = ok and payload.get("error_code") == expect_error_code
        elif completed.returncode == 0:
            ok = ok and payload.get("ok") is True
        return {
            "args": args,
            "cwd": str(cwd) if cwd is not None else None,
            "exit_code": completed.returncode,
            "expected_exit": list(expected_exits),
            "error_code": payload.get("error_code"),
            "expected_error_code": expect_error_code,
            "ok": ok,
            "stdout": completed.stdout.strip(),
            "stderr": completed.stderr.strip(),
            "payload": payload,
        }

    def materialize_fixture(self, fixture: dict[str, Any], project: Path, acf_home: Path) -> Path:
        context = project / "docs" / "ai"
        seed_profile = str(fixture.get("seed_profile") or fixture.get("profile") or "minimal")
        init_step = self.run_acf(
            ["init", str(context), "--profile", seed_profile, "--json"],
            env_extra={"ACF_HOME": str(acf_home)},
        )
        if not init_step["ok"]:
            raise RuntimeError(f"failed to seed fixture {fixture['fixture']}: {init_step}")

        for rel in fixture.get("remove_paths", []):
            target = context / rel
            if target.is_dir():
                shutil.rmtree(target)
            elif target.exists():
                target.unlink()

        for rel, text in fixture.get("files", {}).items():
            target = context / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(str(text), encoding="utf-8")

        for rel, text in fixture.get("root_files", {}).items():
            target = project / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(str(text), encoding="utf-8")

        return context

    def assert_preserved(self, fixture: dict[str, Any], context: Path, errors: list[str]) -> None:
        for item in fixture.get("preserve_contains", []):
            target = context / item["path"]
            text = target.read_text(encoding="utf-8") if target.exists() else ""
            if item["text"] not in text:
                errors.append(f"{fixture['fixture']}: expected preserved text in {item['path']}")

    def assert_marker_notes_idempotent(self, context: Path, errors: list[str]) -> None:
        for rel in ("AGENTS.md", "reference/System_Manual.md"):
            path = context / rel
            if not path.exists():
                continue
            text = path.read_text(encoding="utf-8")
            if text.count("<!-- ACF:UPGRADE-NOTES:START -->") > 1:
                errors.append(f"{rel}: repeated upgrade notes marker")

    def assert_expected_exists(self, fixture: dict[str, Any], context: Path, errors: list[str]) -> None:
        for rel in fixture.get("expect_exists", []):
            if not (context / rel).exists():
                errors.append(f"{fixture['fixture']}: expected {rel} to exist after upgrade")

    def run_main_fixture(self, fixture: dict[str, Any], tmp: Path) -> dict[str, Any]:
        project = tmp / fixture["fixture"]
        acf_home = tmp / f"{fixture['fixture']}-acf-home"
        context = self.materialize_fixture(fixture, project, acf_home)
        steps: list[dict[str, Any]] = []
        errors: list[str] = []

        self.assert_preserved(fixture, context, errors)
        steps.append(
            self.run_acf(
                ["status", str(context), "--json"],
                expect_exit=(0, 1),
                env_extra={"ACF_HOME": str(acf_home)},
            )
        )
        dry = self.run_acf(
            ["upgrade", str(context), "--dry-run", "--json"],
            env_extra={"ACF_HOME": str(acf_home)},
        )
        steps.append(dry)
        dry_changed = set(dry["payload"].get("changed_files", []))

        applied = self.run_acf(
            ["upgrade", str(context), "--check-after", "--json"],
            env_extra={"ACF_HOME": str(acf_home)},
        )
        steps.append(applied)
        applied_changed = set(applied["payload"].get("changed_files", []))
        if dry_changed != applied_changed:
            errors.append(f"{fixture['fixture']}: dry-run changed_files differ from actual changed_files")

        second_dry = self.run_acf(
            ["upgrade", str(context), "--dry-run", "--json"],
            env_extra={"ACF_HOME": str(acf_home)},
        )
        steps.append(second_dry)
        if second_dry["payload"].get("changed_files"):
            errors.append(f"{fixture['fixture']}: second upgrade dry-run still reports changes")

        strict = self.run_acf(
            ["check", str(context), "--strict", "--json"],
            expect_exit=(0, 1),
            env_extra={"ACF_HOME": str(acf_home)},
        )
        steps.append(strict)
        if strict["exit_code"] != 0 and not strict["payload"].get("next_actions"):
            errors.append(f"{fixture['fixture']}: strict failure has no next_actions")

        review = self.run_acf(
            ["review", "stale", str(context), "--today", DEFAULT_TODAY, "--json"],
            env_extra={"ACF_HOME": str(acf_home)},
        )
        steps.append(review)
        if fixture.get("expect_stale") and review["payload"].get("summary", {}).get("total", 0) <= 0:
            errors.append(f"{fixture['fixture']}: expected stale signals")

        before_drafts = sorted((context / "worklog" / "curation-drafts").glob("*.md")) if (context / "worklog" / "curation-drafts").exists() else []
        curate = self.run_acf(
            ["curate", "draft", str(context), "--today", DEFAULT_TODAY, "--dry-run", "--json"],
            env_extra={"ACF_HOME": str(acf_home)},
        )
        steps.append(curate)
        after_drafts = sorted((context / "worklog" / "curation-drafts").glob("*.md")) if (context / "worklog" / "curation-drafts").exists() else []
        if before_drafts != after_drafts:
            errors.append(f"{fixture['fixture']}: curate dry-run wrote files")

        self.assert_preserved(fixture, context, errors)
        self.assert_marker_notes_idempotent(context, errors)
        self.assert_expected_exists(fixture, context, errors)

        return {
            "fixture": fixture["fixture"],
            "kind": "main",
            "source_version": fixture.get("source_version"),
            "risk_tags": fixture.get("risk_tags", []),
            "ok": all(step["ok"] for step in steps) and not errors,
            "errors": errors,
            "steps": steps,
            "tmp": str(project),
        }

    def run_curation_collision_fixture(self, fixture: dict[str, Any], tmp: Path) -> dict[str, Any]:
        project = tmp / fixture["fixture"]
        acf_home = tmp / f"{fixture['fixture']}-acf-home"
        context = self.materialize_fixture(fixture, project, acf_home)
        steps: list[dict[str, Any]] = []
        errors: list[str] = []

        first = self.run_acf(
            ["curate", "draft", str(context), "--today", DEFAULT_TODAY, "--json"],
            env_extra={"ACF_HOME": str(acf_home)},
        )
        steps.append(first)
        if first["payload"].get("created") is not True:
            errors.append(f"{fixture['fixture']}: expected first curate draft to create a file")
        draft_path = first["payload"].get("draft_path")
        if draft_path and not (context / str(draft_path)).exists():
            errors.append(f"{fixture['fixture']}: reported draft_path does not exist")

        second = self.run_acf(
            ["curate", "draft", str(context), "--today", DEFAULT_TODAY, "--json"],
            expect_exit=3,
            expect_error_code="curation_draft_exists",
            env_extra={"ACF_HOME": str(acf_home)},
        )
        steps.append(second)

        return {
            "fixture": fixture["fixture"],
            "kind": "curation_collision",
            "source_version": fixture.get("source_version"),
            "risk_tags": fixture.get("risk_tags", []),
            "ok": all(step["ok"] for step in steps) and not errors,
            "errors": errors,
            "steps": steps,
            "tmp": str(project),
        }

    def run_fixture(self, fixture: dict[str, Any], tmp: Path) -> dict[str, Any]:
        if fixture.get("scenario") == "curation_collision":
            return self.run_curation_collision_fixture(fixture, tmp)
        return self.run_main_fixture(fixture, tmp)

    def run(self, fixtures: list[dict[str, Any]]) -> dict[str, Any]:
        results: list[dict[str, Any]] = []
        tmp_path = Path(tempfile.mkdtemp(prefix="acf-upgrade-matrix-"))
        try:
            for fixture in fixtures:
                try:
                    result = self.run_fixture(fixture, tmp_path)
                except Exception as exc:  # pragma: no cover - defensive runner boundary
                    result = {
                        "fixture": fixture["fixture"],
                        "source_version": fixture.get("source_version"),
                        "risk_tags": fixture.get("risk_tags", []),
                        "ok": False,
                        "errors": [str(exc)],
                        "steps": [],
                    }
                if not self.keep_tmp:
                    result.pop("tmp", None)
                results.append(result)
        finally:
            if not self.keep_tmp:
                shutil.rmtree(tmp_path, ignore_errors=True)
        return {
            "schema_version": 1,
            "command": "upgrade_matrix",
            "ok": all(result["ok"] for result in results),
            "fixture_count": len(results),
            "results": results,
        }


def run_matrix(
    *,
    mode: str = "quick",
    acf_cmd: list[str] | None = None,
    keep_tmp: bool = False,
) -> dict[str, Any]:
    command = acf_cmd or [sys.executable, str(ROOT / "acf.py")]
    runner = UpgradeMatrixRunner(command, keep_tmp=keep_tmp)
    return runner.run(discover_fixtures(mode))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run acf upgrade compatibility fixtures.")
    parser.add_argument("--mode", choices=("quick", "full"), default="quick")
    parser.add_argument("--acf", nargs="+", default=None, help="acf command prefix, for example: uv run acf")
    parser.add_argument("--keep-tmp", action="store_true", help="include temp paths in JSON output")
    args = parser.parse_args(argv)

    payload = run_matrix(mode=args.mode, acf_cmd=args.acf, keep_tmp=args.keep_tmp)
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":  # pragma: no cover - script entry
    raise SystemExit(main())
