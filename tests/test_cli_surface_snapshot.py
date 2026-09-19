"""Snapshot the full CLI surface so parser composition cannot drift silently.

Moving an inline sub-parser out of ``runtime.build_parser`` into a module-level
``register_*_parser`` is a mechanical edit, but ``argparse`` makes it easy to
change behaviour by accident: a dropped ``dest``, a flag that becomes required, a
changed default or a lost ``func`` binding all keep the CLI "working" while
changing the JSON contract.

``tests/fixtures/cli_surface.json`` is the frozen surface captured before those
moves. Regenerate it deliberately (never to silence a failure):

    uv run python tests/test_cli_surface_snapshot.py --write
"""

from __future__ import annotations

import argparse
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "cli_surface.json"


def _describe_action(action: argparse.Action) -> str:
    """One compact, reviewable token per argparse action."""

    choices = action.choices
    if isinstance(choices, (list, tuple, set, frozenset)):
        rendered = ",".join(sorted(map(str, choices)))
    else:
        rendered = ""
    default = "suppressed" if action.default is argparse.SUPPRESS else repr(action.default)
    return "|".join(
        (
            ",".join(action.option_strings) or "(positional)",
            action.dest,
            str(action.nargs),
            default,
            rendered,
        )
    )


def _describe_parser(parser: argparse.ArgumentParser) -> dict[str, object]:
    handler = parser.get_default("func")
    return {
        "handler": None
        if handler is None
        else f"{getattr(handler, '__module__', '?')}.{getattr(handler, '__qualname__', '?')}",
        "actions": sorted(
            _describe_action(action)
            for action in parser._actions
            if not isinstance(action, argparse._SubParsersAction)
        ),
    }


def cli_surface() -> dict[str, object]:
    from ai_context_framework import runtime

    surface: dict[str, object] = {}

    def walk(parser: argparse.ArgumentParser, prefix: str) -> None:
        for action in parser._actions:
            if not isinstance(action, argparse._SubParsersAction):
                continue
            for name, sub in sorted(action.choices.items()):
                path = f"{prefix} {name}".strip()
                surface[path] = _describe_parser(sub)
                walk(sub, path)

    root = runtime.build_parser()
    surface["(root)"] = _describe_parser(root)
    walk(root, "")
    return surface


class CliSurfaceSnapshotTests(unittest.TestCase):
    def test_cli_surface_matches_snapshot(self) -> None:
        self.assertTrue(FIXTURE.is_file(), f"missing fixture {FIXTURE}")
        expected = json.loads(FIXTURE.read_text(encoding="utf-8"))
        actual = json.loads(json.dumps(cli_surface(), ensure_ascii=False))
        self.assertEqual(
            sorted(actual),
            sorted(expected),
            "command inventory changed",
        )
        for path in sorted(expected):
            self.assertEqual(actual[path], expected[path], f"surface changed for {path!r}")


def _write_fixture() -> int:
    payload = json.dumps(
        cli_surface(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE.write_text(payload + "\n", encoding="utf-8")
    print(f"wrote {FIXTURE.relative_to(ROOT).as_posix()} ({len(payload)} chars)")
    return 0


if __name__ == "__main__":
    if "--write" in sys.argv:
        raise SystemExit(_write_fixture())
    unittest.main()
