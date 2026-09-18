"""Isolated continuation owner-context verification fixture.

The fixture creates a throwaway git repository plus a *sibling* temporary
ACF_HOME (never inside the worktree), initializes a minimal continuation,
obtains an owner-context capability handle without reading its content, and then
runs the documented owner-protected follow-ups in the same argv shape that
scheduler wrappers use:

    assert-owner -> progress -> release --handoff

The fixture can only prove ACF-side behaviour. Whether a web/MCP toolchain
blocks ``--owner-file`` *before* ACF runs must be answered inside that toolchain
with the same argv shape; that check is recorded as a pending acceptance item in
``docs/ai/reference/Continuation_Owner_Context_Verification.md``.
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


PARSER_LAYER_TOKENS = ("invalid", "argument", "usage", "input")
OWNER_LAYER_TOKENS = ("owner", "credential", "lease", "generation", "fence", "binding")


def parse_json_output(stdout: str) -> dict[str, Any] | None:
    text = stdout.strip()
    if not text:
        return None
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            value = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    return value if isinstance(value, dict) else None


def classify_layer(step: dict[str, Any]) -> str:
    """Classify where a failed owner-protected step failed."""
    if step["ok"]:
        return "ok"
    payload = step.get("payload")
    if not isinstance(payload, dict):
        return "pre_acf"
    code = str(payload.get("error_code") or "").lower()
    if any(token in code for token in PARSER_LAYER_TOKENS):
        return "acf_parser"
    if any(token in code for token in OWNER_LAYER_TOKENS):
        return "acf_owner_binding"
    return "acf_runtime"


class OwnerContextFixture:
    def __init__(self, acf_cmd: list[str], keep_tmp: bool) -> None:
        self.acf_cmd = acf_cmd
        self.keep_tmp = keep_tmp
        self.steps: list[dict[str, Any]] = []
        self.workspace = Path(tempfile.mkdtemp(prefix="acf-owner-fixture-"))
        self.acf_home = Path(tempfile.mkdtemp(prefix="acf-owner-fixture-home-"))
        self.env = os.environ.copy()
        self.env["PYTHONUTF8"] = "1"
        self.env["ACF_HOME"] = str(self.acf_home)

    def cleanup(self) -> None:
        if self.keep_tmp:
            return
        shutil.rmtree(self.workspace, ignore_errors=True)
        shutil.rmtree(self.acf_home, ignore_errors=True)

    def _record(
        self,
        name: str,
        argv: list[str],
        completed: subprocess.CompletedProcess[str],
        *,
        expect_exit: int = 0,
    ) -> dict[str, Any]:
        payload = parse_json_output(completed.stdout)
        step: dict[str, Any] = {
            "name": name,
            "argv": argv,
            "exit_code": completed.returncode,
            "expected_exit": expect_exit,
            "error_code": (payload or {}).get("error_code"),
            "stderr": completed.stderr.strip(),
            "ok": completed.returncode == expect_exit,
            "payload": payload,
        }
        step["layer"] = classify_layer(step)
        self.steps.append(step)
        return step

    def run_acf(self, name: str, args: list[str], *, expect_exit: int = 0) -> dict[str, Any]:
        completed = subprocess.run(
            [*self.acf_cmd, *args],
            cwd=str(self.workspace),
            env=self.env,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        return self._record(name, [*self.acf_cmd, *args], completed, expect_exit=expect_exit)

    def run_git(self, name: str, args: list[str]) -> dict[str, Any]:
        completed = subprocess.run(
            ["git", *args],
            cwd=str(self.workspace),
            env=self.env,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        return self._record(name, ["git", *args], completed)

    def prepare_workspace(self) -> None:
        context = self.workspace / "docs" / "ai"
        context.mkdir(parents=True, exist_ok=True)
        self.run_git("git init", ["init", "-q", "."])
        self.run_git(
            "git initial commit",
            [
                "-c",
                "user.email=fixture@example.invalid",
                "-c",
                "user.name=fixture",
                "commit",
                "-q",
                "--allow-empty",
                "-m",
                "fixture baseline",
            ],
        )
        self.run_acf("acf init", ["init", str(context), "--profile", "minimal", "--json"])

    def run(self) -> dict[str, Any]:
        task_id = "FIXTURE01"
        try:
            self.prepare_workspace()
            self.run_acf(
                "continuation init",
                [
                    "continuation",
                    "init",
                    str(self.workspace),
                    "--task-id",
                    task_id,
                    "--title",
                    "Owner-context fixture",
                    "--objective",
                    "Verify owner-context transport in isolation",
                    "--json",
                ],
            )
            claim = self.run_acf(
                "continuation claim",
                [
                    "continuation",
                    "claim",
                    str(self.workspace),
                    "--task-id",
                    task_id,
                    "--runner-id",
                    "owner-context-fixture",
                    "--json",
                ],
            )
            claim_payload = claim.get("payload") or {}
            owner_context = claim_payload.get("owner_context") or {}
            handle_value = str(owner_context.get("handle") or "")
            handle = Path(handle_value) if handle_value else None
            handle_exists = bool(handle) and handle.is_file()
            # The fixture must never read the handle content, only confirm the
            # capability file exists inside the isolated ACF_HOME.
            self.steps.append(
                {
                    "name": "owner-context handle issued",
                    "argv": [],
                    "exit_code": 0,
                    "expected_exit": 0,
                    "error_code": None,
                    "stderr": "",
                    "ok": handle_exists,
                    "layer": "ok" if handle_exists else "pre_acf",
                    "payload": {
                        "transport": owner_context.get("transport"),
                        "handle_inside_isolated_home": bool(handle) and self.acf_home in handle.parents,
                        "handle_size": handle.stat().st_size if handle_exists and handle else None,
                    },
                }
            )
            if not handle_exists:
                return self._result(claim)

            owner_args = ["--task-id", task_id, "--owner-file", str(handle)]
            self.run_acf(
                "assert-owner",
                ["continuation", "assert-owner", str(self.workspace), *owner_args, "--json"],
            )
            self.run_acf(
                "progress",
                [
                    "continuation",
                    "progress",
                    str(self.workspace),
                    *owner_args,
                    "--phase",
                    "executing",
                    "--milestone",
                    "owner-context fixture progress",
                    "--json",
                ],
            )
            self.run_acf(
                "release",
                [
                    "continuation",
                    "release",
                    str(self.workspace),
                    *owner_args,
                    "--handoff",
                    "--json",
                ],
            )
            return self._result(claim)
        finally:
            self.cleanup()

    def _result(self, claim_step: dict[str, Any]) -> dict[str, Any]:
        owner_steps = [step for step in self.steps if step["name"] in {"assert-owner", "progress", "release"}]
        acf_side_ok = all(step["ok"] for step in owner_steps) and bool(owner_steps)
        return {
            "schema_version": 1,
            "command": "continuation_owner_fixture",
            "ok": acf_side_ok,
            "acf": self.acf_cmd,
            "acf_home": str(self.acf_home),
            "workspace": str(self.workspace),
            "acf_side_verdict": "acf_side_ok" if acf_side_ok else "acf_side_failed",
            "real_chain_status": "not_verified_here",
            "real_chain_note": (
                "Real web/MCP toolchain reproduction cannot run inside this repository; "
                "rerun the same argv shape in the scheduler toolchain and classify the failing layer."
            ),
            "steps": [
                {key: value for key, value in step.items() if key != "payload"} | {"error_code": step["error_code"]}
                for step in self.steps
            ],
            "next_actions": [
                "Re-run `assert-owner`, `progress` and `release --handoff` with the same --owner-file shape in the real scheduler toolchain.",
                "If the command never reaches ACF there, fix the connector invocation contract instead of ACF credential validation.",
            ],
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the isolated owner-context verification fixture.")
    parser.add_argument(
        "--acf",
        nargs="+",
        default=["acf"],
        help="acf command argv prefix, for example: --acf uv run acf",
    )
    parser.add_argument("--keep-tmp", action="store_true", help="keep temporary directories for debugging")
    args = parser.parse_args(argv)

    result = OwnerContextFixture(args.acf, args.keep_tmp).run()
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
