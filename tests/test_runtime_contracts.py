"""Contract tests for the explicit runtime namespace export allowlist.

``ai_context_framework.runtime_exports.RUNTIME_PART_EXPORTS`` replaced the old
"merge the whole ``__dict__``" behaviour. These tests keep that table honest:

* it must stay exactly equal to the export set recomputed from the source by
  ``scripts/runtime_export_audit.py``;
* the only dunder that may be merged is the documented PEP 562 ``__getattr__``
  forwarding hook;
* narrowing the merge must not orphan any name that a part module or a consumer
  module reads;
* :func:`install_runtime_parts` must fail closed on an undeclared part module, a
  declared name that does not exist, an un-wired declaration, and a same-name
  different-object collision.
"""

from __future__ import annotations

import json
import subprocess
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from ai_context_framework import runtime_exports


ROOT = Path(__file__).resolve().parents[1]
DUNDER_EXPORT_ALLOWLIST = {"archive_workstream": ["__getattr__"]}


class RuntimeExportContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        completed = subprocess.run(
            [sys.executable, "scripts/runtime_export_audit.py", "--json"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if completed.returncode != 0:
            raise AssertionError(
                "runtime_export_audit.py failed: "
                f"{completed.stdout.strip()}\n{completed.stderr.strip()}"
            )
        cls.report = json.loads(completed.stdout)

    def test_export_table_matches_required_exports(self) -> None:
        declared = {
            component: {name for name in names if not name.startswith("__")}
            for component, names in runtime_exports.RUNTIME_PART_EXPORTS.items()
        }
        required = {
            component: set(names)
            for component, names in self.report["required_exports"].items()
        }
        self.assertEqual(declared, required)

    def test_only_documented_dunder_exports(self) -> None:
        dunders = {
            component: sorted(name for name in names if name.startswith("__"))
            for component, names in runtime_exports.RUNTIME_PART_EXPORTS.items()
        }
        self.assertEqual(
            {component: names for component, names in dunders.items() if names},
            DUNDER_EXPORT_ALLOWLIST,
        )

    def test_declared_exports_exist_in_their_modules(self) -> None:
        import importlib

        for component, names in runtime_exports.RUNTIME_PART_EXPORTS.items():
            module = importlib.import_module(
                f"ai_context_framework.runtime_parts.{component}"
            )
            missing = sorted(name for name in names if name not in vars(module))
            self.assertEqual(missing, [], f"{component} declares missing names")

    def test_merge_has_no_different_object_collisions(self) -> None:
        self.assertEqual(self.report["different_object_collisions"], [])

    def test_narrowed_merge_stays_closed(self) -> None:
        self.assertEqual(self.report["part_closure_gaps"], {})
        self.assertEqual(self.report["consumer_injection_gaps"], {})
        self.assertEqual(self.report["dynamic_access_gaps"], [])

    def test_narrowed_merge_is_smaller_than_the_previous_behaviour(self) -> None:
        injected = self.report["injected_after_narrowing_count"]
        exported = self.report["exported_name_count"]
        runtime_own = self.report["runtime_own_top_level_count"]
        self.assertLess(injected, runtime_own + exported)

    def test_install_is_fail_closed(self) -> None:
        def module(component: str, **names: object) -> types.ModuleType:
            built = types.ModuleType(f"ai_context_framework.runtime_parts.{component}")
            for name, value in names.items():
                setattr(built, name, value)
            return built

        shared = object()
        cases = {
            "undeclared part module": (
                {"core": ("present",)},
                [module("other", present=shared)],
            ),
            "declared name missing": (
                {"core": ("absent",)},
                [module("core", present=shared)],
            ),
            "declared module not wired in": (
                {"core": ("present",), "objects": ("present",)},
                [module("core", present=shared)],
            ),
            "same name different object": (
                {"core": ("duplicate",), "objects": ("duplicate",)},
                [module("core", duplicate=shared), module("objects", duplicate=object())],
            ),
        }
        for label, (table, modules) in cases.items():
            with self.subTest(label=label), patch.dict(
                runtime_exports.RUNTIME_PART_EXPORTS, table, clear=True
            ):
                with self.assertRaises(runtime_exports.RuntimeExportError):
                    runtime_exports.install_runtime_parts({}, modules)

    def test_install_allows_same_name_same_object(self) -> None:
        shared = object()
        core = types.ModuleType("ai_context_framework.runtime_parts.core")
        core.duplicate = shared
        objects = types.ModuleType("ai_context_framework.runtime_parts.objects")
        objects.duplicate = shared
        namespace: dict[str, object] = {}
        with patch.dict(
            runtime_exports.RUNTIME_PART_EXPORTS,
            {"core": ("duplicate",), "objects": ("duplicate",)},
            clear=True,
        ):
            runtime_exports.install_runtime_parts(namespace, [core, objects])
        self.assertIs(namespace["duplicate"], shared)
        self.assertIs(vars(core)["duplicate"], shared)

    def test_consumer_name_tuples_match_measured_free_names(self) -> None:
        import ai_context_framework.runtime_context as runtime_context

        expected = {
            "ai_context_framework/commands/workstream.py": list(
                runtime_context.WORKSTREAM_CONSUMER_NAMES
            ),
            "ai_context_framework/commands/workstream_reserve.py": list(
                runtime_context.WORKSTREAM_RESERVE_CONSUMER_NAMES
            ),
        }
        measured = {
            relative: sorted(row["free_names"])
            for relative, row in self.report["consumers"].items()
        }
        self.assertEqual(
            {relative: sorted(names) for relative, names in expected.items()},
            measured,
        )

    def test_build_runtime_context_is_fail_closed(self) -> None:
        import ai_context_framework.runtime_context as runtime_context

        with self.assertRaises(runtime_context.RuntimeContextError):
            runtime_context.build_runtime_context(
                {"present": 1}, ("present", "absent"), label="probe"
            )
        context = runtime_context.build_runtime_context(
            {"present": 1, "other": 2}, ("present",), label="probe"
        )
        self.assertEqual(context.as_binding(), {"present": 1})
        self.assertEqual(context.resolve("present"), 1)
        with self.assertRaises(runtime_context.RuntimeContextError):
            context.resolve("other")

    def test_workstream_context_is_bounded(self) -> None:
        """The Workstream consumer must receive a small explicit subset, not the merge."""

        from ai_context_framework.runtime_parts import archive_workstream

        context = archive_workstream.workstream_context()
        imported = __import__(
            "ai_context_framework.runtime", fromlist=["runtime"]
        )
        merged_public = {
            name for name in vars(imported) if not name.startswith("__")
        }
        self.assertEqual(
            len(context.names), len(set(context.names))
        )
        self.assertLess(len(context.names), len(merged_public))

    def test_lazy_compat_getattr_is_preserved(self) -> None:
        """The merged ``__getattr__`` must keep forwarding workstream helpers."""

        import acf

        workstream = __import__(
            "ai_context_framework.commands.workstream", fromlist=["workstream"]
        )
        self.assertTrue(hasattr(acf, "parse_workstream_archive_date"))
        self.assertIs(
            acf.parse_workstream_archive_date,
            workstream.parse_workstream_archive_date,
        )


if __name__ == "__main__":
    unittest.main()
