"""Run the smallest release smoke suite for acf.

The runner intentionally calls the acf CLI through subprocess argument lists.
It does not import acf internals and does not use shell command strings.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


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


class SmokeRunner:
    def __init__(self, acf_cmd: list[str], keep_tmp: bool) -> None:
        self.acf_cmd = acf_cmd
        self.keep_tmp = keep_tmp
        self.scenarios: list[dict[str, Any]] = []

    def run_acf(
        self,
        args: list[str],
        *,
        cwd: Path | None = None,
        expect_exit: int = 0,
        expect_error_code: str | None = None,
    ) -> dict[str, Any]:
        env = os.environ.copy()
        env.setdefault("PYTHONUTF8", "1")
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
        ok = completed.returncode == expect_exit
        if expect_error_code is not None:
            ok = ok and payload.get("error_code") == expect_error_code
        if expect_error_code is None and expect_exit == 0:
            ok = ok and payload.get("ok") is True
        return {
            "args": args,
            "cwd": str(cwd) if cwd is not None else None,
            "exit_code": completed.returncode,
            "expected_exit": expect_exit,
            "error_code": payload.get("error_code"),
            "expected_error_code": expect_error_code,
            "ok": ok,
            "stderr": completed.stderr.strip(),
            "payload": payload,
        }

    def scenario(self, name: str, func: Any) -> None:
        with tempfile.TemporaryDirectory(prefix="acf-smoke-") as tmp:
            tmp_path = Path(tmp)
            record: dict[str, Any] = {"name": name, "ok": False, "tmp": str(tmp_path), "steps": []}
            try:
                func(tmp_path, record["steps"])
                record["ok"] = all(step["ok"] for step in record["steps"])
            except Exception as exc:  # pragma: no cover - defensive runner boundary
                record["error"] = str(exc)
            if not self.keep_tmp:
                record.pop("tmp", None)
            self.scenarios.append(record)

    def init_status_check(self, tmp: Path, steps: list[dict[str, Any]]) -> None:
        project = tmp / "init-status-check"
        context = project / "docs" / "ai"
        nested = project / "src" / "nested"
        nested.mkdir(parents=True)
        steps.append(self.run_acf(["init", str(context), "--profile", "standard", "--json"]))
        steps.append(self.run_acf(["status", "--json"], cwd=nested))
        steps.append(self.run_acf(["check", "--json"], cwd=nested))

    def worklog_create_append_error_code(self, tmp: Path, steps: list[dict[str, Any]]) -> None:
        context = tmp / "worklog" / "docs" / "ai"
        date = "2099-01-01"
        steps.append(self.run_acf(["init", str(context), "--profile", "standard", "--json"]))
        steps.append(
            self.run_acf(
                [
                    "new",
                    "worklog",
                    str(context),
                    "--date",
                    date,
                    "--summary",
                    "smoke create",
                    "--json",
                ]
            )
        )
        steps.append(
            self.run_acf(
                [
                    "new",
                    "worklog",
                    str(context),
                    "--date",
                    date,
                    "--summary",
                    "smoke duplicate",
                    "--json",
                ],
                expect_exit=3,
                expect_error_code="TARGET_EXISTS_APPEND_REQUIRED",
            )
        )
        steps.append(
            self.run_acf(
                [
                    "new",
                    "worklog",
                    str(context),
                    "--date",
                    date,
                    "--summary",
                    "smoke append",
                    "--append",
                    "--json",
                ]
            )
        )
        steps.append(
            self.run_acf(
                [
                    "new",
                    "worklog",
                    str(context),
                    "--date",
                    date,
                    "--summary",
                    "smoke conflict",
                    "--append",
                    "--force",
                    "--json",
                ],
                expect_exit=2,
                expect_error_code="APPEND_FORCE_CONFLICT",
            )
        )

    def workstream_minimal_happy_path(self, tmp: Path, steps: list[dict[str, Any]]) -> None:
        context = tmp / "workstream" / "docs" / "ai"
        steps.append(self.run_acf(["init", str(context), "--profile", "standard", "--json"]))
        steps.append(self.run_acf(["workstream", "init", str(context), "--json"]))
        steps.append(
            self.run_acf(
                [
                    "workstream",
                    "add",
                    str(context),
                    "--id",
                    "WS001",
                    "--title",
                    "Smoke workstream",
                    "--owner",
                    "smoke",
                    "--goal",
                    "Verify the minimal happy path.",
                    "--output",
                    "Smoke evidence",
                    "--json",
                ]
            )
        )
        steps.append(
            self.run_acf(
                [
                    "workstream",
                    "merge-request",
                    "WS001",
                    str(context),
                    "--target",
                    "active/Context.md",
                    "--summary",
                    "Smoke merge candidate",
                    "--verification",
                    "Smoke verification passed",
                    "--json",
                ]
            )
        )
        steps.append(
            self.run_acf(
                [
                    "workstream",
                    "set",
                    "WS001",
                    str(context),
                    "--status",
                    "Active",
                    "--json",
                ]
            )
        )
        steps.append(
            self.run_acf(
                [
                    "workstream",
                    "stage",
                    "add",
                    "WS001",
                    str(context),
                    "--id",
                    "WS001.1",
                    "--title",
                    "Stage one",
                    "--json",
                ]
            )
        )
        steps.append(self.run_acf(["workstream", "focus", "WS001", "WS001.1", str(context), "--json"]))
        steps.append(
            self.run_acf(
                [
                    "workstream",
                    "stage",
                    "done",
                    "WS001",
                    "WS001.1",
                    str(context),
                    "--evidence",
                    "Smoke stage evidence",
                    "--clear-current",
                    "--json",
                ]
            )
        )
        steps.append(self.run_acf(["workstream", "ready", "WS001", str(context), "--json"]))
        steps.append(
            self.run_acf(
                [
                    "workstream",
                    "done",
                    "WS001",
                    str(context),
                    "--evidence",
                    "Smoke evidence",
                    "--merge-resolution",
                    "merged",
                    "--json",
                ]
            )
        )
        steps.append(self.run_acf(["check", str(context), "--json"]))

    def run(self) -> dict[str, Any]:
        self.scenario("init -> nested status/check", self.init_status_check)
        self.scenario("worklog create/append/error_code", self.worklog_create_append_error_code)
        self.scenario("workstream minimal happy path", self.workstream_minimal_happy_path)
        ok = all(scenario["ok"] for scenario in self.scenarios)
        return {
            "schema_version": 1,
            "command": "minimal_smoke",
            "ok": ok,
            "acf": self.acf_cmd,
            "scenarios": self.scenarios,
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the minimal acf smoke suite.")
    parser.add_argument(
        "--acf",
        nargs="+",
        default=["acf"],
        help="acf command argv prefix, for example: --acf uv run acf",
    )
    parser.add_argument("--keep-tmp", action="store_true", help="keep temporary directories for debugging")
    args = parser.parse_args(argv)

    result = SmokeRunner(args.acf, args.keep_tmp).run()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
