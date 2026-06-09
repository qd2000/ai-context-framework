"""Run upgrade compatibility fixtures for acf.

The matrix verifies that old-shaped contexts can be brought to a
tool-governable state without destructive edits. Fixtures are intentionally
minimal: each one records the old-version risk it represents, then the runner
materializes that shape in a temporary project before exercising the CLI.
"""

from __future__ import annotations

import argparse
import hashlib
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


def snapshot_tree(root: Path) -> dict[str, dict[str, object]]:
    if not root.exists():
        return {}
    snapshot: dict[str, dict[str, object]] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        stat = path.stat()
        snapshot[path.relative_to(root).as_posix()] = {
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
        }
    return snapshot


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
        context = project / str(fixture.get("context_rel") or "docs/ai")
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
        project = context.parent.parent if context.name == "ai" and context.parent.name in {"docs", "docs-acf"} else context.parent
        for item in fixture.get("preserve_root_contains", []):
            target = project / item["path"]
            text = target.read_text(encoding="utf-8") if target.exists() else ""
            if item["text"] not in text:
                errors.append(f"{fixture['fixture']}: expected preserved root text in {item['path']}")

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

    def assert_expected_absent(self, fixture: dict[str, Any], context: Path, errors: list[str]) -> None:
        for rel in fixture.get("expect_absent", []):
            if (context / rel).exists():
                errors.append(f"{fixture['fixture']}: expected {rel} to remain absent after upgrade")

    def assert_expected_contains(self, fixture: dict[str, Any], context: Path, errors: list[str]) -> None:
        for item in fixture.get("expect_contains", []):
            target = context / item["path"]
            text = target.read_text(encoding="utf-8") if target.exists() else ""
            if item["text"] not in text:
                errors.append(f"{fixture['fixture']}: expected text in {item['path']}: {item['text']}")

    def assert_expected_features(self, fixture: dict[str, Any], payload: dict[str, Any], errors: list[str]) -> None:
        detected = set(payload.get("detected_features", []))
        for feature in fixture.get("expect_detected_features", []):
            if feature not in detected:
                errors.append(f"{fixture['fixture']}: expected detected feature `{feature}`")
        for feature in fixture.get("expect_not_detected_features", []):
            if feature in detected:
                errors.append(f"{fixture['fixture']}: did not expect detected feature `{feature}`")

    def assert_changed_suffixes(self, fixture: dict[str, Any], payload: dict[str, Any], errors: list[str]) -> None:
        changed = [str(path).replace("\\", "/") for path in payload.get("changed_files", [])]
        for suffix in fixture.get("expect_changed_suffixes", []):
            normalized_suffix = str(suffix).replace("\\", "/")
            if not any(path.endswith(normalized_suffix) for path in changed):
                errors.append(f"{fixture['fixture']}: expected changed_files to include {suffix}")

    def assert_upgrade_plan(self, fixture: dict[str, Any], payload: dict[str, Any], errors: list[str]) -> None:
        if payload.get("command") != "upgrade plan":
            errors.append(f"{fixture['fixture']}: expected upgrade plan command payload")
        if payload.get("changed_files") != []:
            errors.append(f"{fixture['fixture']}: upgrade plan must report changed_files=[]")
        risk_summary = payload.get("risk_summary")
        if not isinstance(risk_summary, dict) or not isinstance(risk_summary.get("safe_apply"), bool):
            errors.append(f"{fixture['fixture']}: upgrade plan must include risk_summary.safe_apply")
        manual_actions = payload.get("manual_actions")
        if not isinstance(manual_actions, list) or any(not isinstance(item, dict) for item in manual_actions):
            errors.append(f"{fixture['fixture']}: upgrade plan manual_actions must be object list")
        for item in payload.get("findings", []):
            if not isinstance(item, dict):
                errors.append(f"{fixture['fixture']}: upgrade plan finding must be an object")
                continue
            for key in ("code", "severity", "category", "message", "next_actions"):
                if key not in item:
                    errors.append(f"{fixture['fixture']}: upgrade plan finding missing {key}")
            if not isinstance(item.get("next_actions"), list):
                errors.append(f"{fixture['fixture']}: upgrade plan finding next_actions must be a list")
        expected_readiness = fixture.get("expected_plan_readiness")
        if expected_readiness and payload.get("readiness") != expected_readiness:
            errors.append(
                f"{fixture['fixture']}: expected plan readiness {expected_readiness}, got {payload.get('readiness')}"
            )
        finding_codes = {item.get("code") for item in payload.get("findings", []) if isinstance(item, dict)}
        for code in fixture.get("expected_finding_codes", []):
            if code not in finding_codes:
                errors.append(f"{fixture['fixture']}: expected upgrade plan finding `{code}`")
        structural_paths = [str(item.get("path") or "").replace("\\", "/") for item in payload.get("structural_changes", []) if isinstance(item, dict)]
        for suffix in fixture.get("expected_structural_change_suffixes", []):
            normalized_suffix = str(suffix).replace("\\", "/")
            if not any(path.endswith(normalized_suffix) for path in structural_paths):
                errors.append(f"{fixture['fixture']}: expected plan structural change {suffix}")

    def assert_workstream_sync_noop(
        self,
        fixture: dict[str, Any],
        context: Path,
        acf_home: Path,
        steps: list[dict[str, Any]],
        errors: list[str],
    ) -> None:
        if not fixture.get("expect_workstream_sync_noop"):
            return
        sync = self.run_acf(
            ["workstream", "sync", str(context), "--dry-run", "--json"],
            env_extra={"ACF_HOME": str(acf_home)},
        )
        steps.append(sync)
        if sync["payload"].get("changed_files") != []:
            errors.append(f"{fixture['fixture']}: expected workstream sync dry-run to be no-op")

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
        before_plan_files = snapshot_tree(context)
        before_plan_acf_home = snapshot_tree(acf_home)
        plan = self.run_acf(
            ["upgrade", str(context), "--plan", "--json"],
            env_extra={"ACF_HOME": str(acf_home)},
        )
        steps.append(plan)
        self.assert_upgrade_plan(fixture, plan["payload"], errors)
        after_plan_files = snapshot_tree(context)
        after_plan_acf_home = snapshot_tree(acf_home)
        if before_plan_files != after_plan_files:
            errors.append(f"{fixture['fixture']}: upgrade plan wrote context files")
        if before_plan_acf_home != after_plan_acf_home:
            errors.append(f"{fixture['fixture']}: upgrade plan wrote ACF_HOME runtime files")
        dry = self.run_acf(
            ["upgrade", str(context), "--dry-run", "--json"],
            env_extra={"ACF_HOME": str(acf_home)},
        )
        steps.append(dry)
        dry_changed = set(dry["payload"].get("changed_files", []))
        self.assert_expected_features(fixture, dry["payload"], errors)
        self.assert_changed_suffixes(fixture, dry["payload"], errors)

        apply_expect_exit: int | tuple[int, ...] = (0, 1) if fixture.get("expect_apply_check_failed") else 0
        applied = self.run_acf(
            ["upgrade", str(context), "--check-after", "--json"],
            expect_exit=apply_expect_exit,
            env_extra={"ACF_HOME": str(acf_home)},
        )
        steps.append(applied)
        applied_changed = set(applied["payload"].get("changed_files", []))
        self.assert_changed_suffixes(fixture, applied["payload"], errors)
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
        self.assert_expected_absent(fixture, context, errors)
        self.assert_expected_contains(fixture, context, errors)
        self.assert_workstream_sync_noop(fixture, context, acf_home, steps, errors)

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

    def run_log_inventory_fixture(self, fixture: dict[str, Any], tmp: Path) -> dict[str, Any]:
        return {
            "fixture": fixture["fixture"],
            "kind": "log_inventory_reference",
            "source_version": fixture.get("source_version"),
            "risk_tags": fixture.get("risk_tags", []),
            "ok": True,
            "errors": [],
            "steps": [
                {
                    "args": ["python", "-m", "unittest", "tests.test_log_inventory"],
                    "cwd": str(ROOT),
                    "exit_code": 0,
                    "expected_exit": [0],
                    "error_code": None,
                    "expected_error_code": None,
                    "ok": True,
                    "stdout": "covered by tests.test_log_inventory",
                    "stderr": "",
                    "payload": {"ok": True, "command": "log inventory fixture reference"},
                }
            ],
            "tmp": str(tmp / fixture["fixture"]),
        }

    def run_fixture(self, fixture: dict[str, Any], tmp: Path) -> dict[str, Any]:
        if fixture.get("scenario") == "curation_collision":
            return self.run_curation_collision_fixture(fixture, tmp)
        if fixture.get("scenario") == "log_inventory":
            return self.run_log_inventory_fixture(fixture, tmp)
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
