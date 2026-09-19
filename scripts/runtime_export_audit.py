"""Audit the implicit runtime namespace merge in the ACF CLI.

``ai_context_framework/runtime.py`` merges the ``__dict__`` of eight
``runtime_parts`` modules into one flat namespace and then writes that merged
namespace back into every part module. The merge is order-sensitive, silent on
collisions, and invisible to static analysis, so this script reports the facts
that a review needs:

1. which top-level names each part module contributes on its own;
2. which contributed names collide across modules, split into "same object"
   (harmless duplicate) and "different object" (a silent shadowing today, and
   exactly what an export allowlist has to reject);
3. which names each consumer command module actually reads from the merged
   namespace (the allowlist candidate set);
4. whether every consumed name is still resolvable from the union of part
   exports plus runtime's own top-level names (closure check).

The script is read-only. It imports the part modules directly and fails closed
if importing them pulls in ``ai_context_framework.runtime``, because that would
pre-merge the namespaces and invalidate the measurement.
"""

from __future__ import annotations

import argparse
import ast
import builtins
import importlib
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIR = ROOT / "ai_context_framework"
RUNTIME_MODULE = "ai_context_framework.runtime"
PART_MODULES = (
    "archive_workstream",
    "check",
    "core",
    "doctor",
    "knowledge_review",
    "objects",
    "plan_task",
    "upgrade",
)
CONSUMER_MODULES = (
    "ai_context_framework/commands/workstream.py",
    "ai_context_framework/commands/workstream_reserve.py",
)
# Names that are only reachable through the merged runtime namespace at runtime:
# ``acf.<name>`` forwards to runtime via ``__getattr__``, and tests/scripts patch
# or read ``runtime.<name>`` / ``<part module>.<name>`` directly.
RUNTIME_ALIASES = ("runtime", "_runtime", "acf", "acf_module")
ATTRIBUTE_SCAN_DIRS = ("tests", "scripts")


class AuditError(RuntimeError):
    pass


def _module_file(relative: str) -> Path:
    path = ROOT / relative
    if not path.is_file():
        raise AuditError(f"missing module file: {relative}")
    return path


def _top_level_bindings(path: Path) -> set[str]:
    """Return every name bound at module top level, including imported names."""

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in tree.body:
        for bound in _binding_targets(node):
            names.add(bound)
    return {name for name in names if not name.startswith("__")}


def _binding_targets(node: ast.AST) -> set[str]:
    found: set[str] = set()
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        found.add(node.name)
    elif isinstance(node, ast.Assign):
        for target in node.targets:
            found |= _target_names(target)
    elif isinstance(node, ast.AnnAssign):
        found |= _target_names(node.target)
    elif isinstance(node, ast.AugAssign):
        found |= _target_names(node.target)
    elif isinstance(node, ast.Import):
        for alias in node.names:
            found.add((alias.asname or alias.name).split(".")[0])
    elif isinstance(node, ast.ImportFrom):
        for alias in node.names:
            found.add(alias.asname or alias.name)
    elif isinstance(node, (ast.For, ast.AsyncFor)):
        found |= _target_names(node.target)
    elif isinstance(node, ast.While):
        pass
    elif isinstance(node, (ast.If, ast.Try, ast.With, ast.AsyncWith)):
        bodies: list[ast.AST] = []
        bodies.extend(getattr(node, "body", []) or [])
        bodies.extend(getattr(node, "orelse", []) or [])
        bodies.extend(getattr(node, "finalbody", []) or [])
        for handler in getattr(node, "handlers", []) or []:
            bodies.extend(getattr(handler, "body", []) or [])
            if getattr(handler, "name", None):
                found.add(str(handler.name))
        for child in bodies:
            for bound in _binding_targets(child):
                found.add(bound)
    return found


def _target_names(node: ast.AST) -> set[str]:
    found: set[str] = set()
    if isinstance(node, ast.Name):
        found.add(node.id)
    elif isinstance(node, (ast.Tuple, ast.List)):
        for element in node.elts:
            found |= _target_names(element)
    elif isinstance(node, ast.Starred):
        found |= _target_names(node.value)
    return found


def _bound_names(tree: ast.AST) -> set[str]:
    """Names bound anywhere in the module: globals, locals, args, targets."""

    bound: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            bound.add(node.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bound.add(node.name)
            args = node.args if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) else None
            if args is not None:
                positional = list(getattr(args, "posonlyargs", [])) + list(args.args)
                for argument in positional + list(args.kwonlyargs):
                    bound.add(argument.arg)
                if args.vararg:
                    bound.add(args.vararg.arg)
                if args.kwarg:
                    bound.add(args.kwarg.arg)
        elif isinstance(node, ast.Lambda):
            args = node.args
            positional = list(getattr(args, "posonlyargs", [])) + list(args.args)
            for argument in positional + list(args.kwonlyargs):
                bound.add(argument.arg)
            if args.vararg:
                bound.add(args.vararg.arg)
            if args.kwarg:
                bound.add(args.kwarg.arg)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            bound.add(node.name)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                bound.add((alias.asname or alias.name).split(".")[0])
        elif isinstance(node, ast.arg):
            bound.add(node.arg)
        elif isinstance(node, ast.alias) and node.asname:
            bound.add(node.asname)
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            bound.update(node.names)
    return bound


def _free_names(path: Path) -> list[str]:
    """Names read by the module that it neither binds itself nor gets from builtins."""

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    used = {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
    }
    unresolved = used - _bound_names(tree) - set(dir(builtins))
    return sorted(unresolved)


def _part_own_names(component: str) -> dict[str, Any]:
    """Import one part module in isolation and describe the names it contributes."""

    module = importlib.import_module(f"ai_context_framework.runtime_parts.{component}")
    namespace = {
        name: value
        for name, value in vars(module).items()
        if not name.startswith("__")
    }
    described = {
        name: {
            "kind": type(value).__name__,
            "origin": getattr(value, "__module__", None),
            "qualname": getattr(value, "__qualname__", None),
        }
        for name, value in namespace.items()
    }
    return {"names": sorted(namespace), "values": namespace, "described": described}


def _attribute_accesses() -> dict[str, list[str]]:
    """Attribute names read off runtime aliases in tests and scripts.

    ``module.__dict__`` injection means these names are resolved dynamically at
    runtime, so static free-name analysis alone cannot see them.
    """

    found: dict[str, set[str]] = {}
    for directory in ATTRIBUTE_SCAN_DIRS:
        root = ROOT / directory
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Attribute):
                    continue
                value = node.value
                if isinstance(value, ast.Name) and value.id in RUNTIME_ALIASES:
                    found.setdefault(value.id, set()).add(node.attr)
    return {alias: sorted(names) for alias, names in found.items()}


def collect() -> dict[str, Any]:
    own: dict[str, list[str]] = {}
    values: dict[str, dict[str, Any]] = {}
    for component in PART_MODULES:
        result = _part_own_names(component)
        own[component] = list(result["names"])
        values[component] = dict(result["values"])

    if RUNTIME_MODULE in sys.modules:
        raise AuditError(
            "importing runtime_parts pulled in ai_context_framework.runtime; "
            "the namespaces were already merged and the audit is invalid"
        )

    providers: dict[str, list[str]] = {}
    for component, names in own.items():
        for name in names:
            providers.setdefault(name, []).append(component)

    collisions: dict[str, Any] = {}
    for name, modules in sorted(providers.items()):
        if len(modules) < 2:
            continue
        first = values[modules[0]][name]
        identical = all(values[module][name] is first for module in modules[1:])
        collisions[name] = {
            "modules": modules,
            "same_object": identical,
            "detail": {
                module: {
                    "kind": type(values[module][name]).__name__,
                    "origin": getattr(values[module][name], "__module__", None),
                    "qualname": getattr(values[module][name], "__qualname__", None),
                }
                for module in modules
            },
        }

    exported = set(providers)
    runtime_own = _top_level_bindings(_module_file("ai_context_framework/runtime.py"))
    workstream_own = _top_level_bindings(_module_file(CONSUMER_MODULES[0]))
    resolvable = exported | runtime_own | workstream_own

    part_free: dict[str, list[str]] = {
        component: _free_names(_module_file(f"ai_context_framework/runtime_parts/{component}.py"))
        for component in PART_MODULES
    }
    consumers: dict[str, Any] = {}
    for relative in CONSUMER_MODULES:
        path = _module_file(relative)
        free = _free_names(path)
        consumers[relative] = {
            "free_names": free,
            "count": len(free),
            "not_resolvable_from_merge": sorted(set(free) - resolvable - set(dir(builtins))),
            "provided_by": {
                name: sorted({module for module in PART_MODULES if name in own[module]})
                or None
                for name in free
            },
        }

    runtime_free = _free_names(_module_file("ai_context_framework/runtime.py"))
    attribute_accesses = _attribute_accesses()

    needed: set[str] = set()
    for free in part_free.values():
        needed.update(free)
    for row in consumers.values():
        needed.update(row["free_names"])
    needed.update(runtime_free)
    for names in attribute_accesses.values():
        needed.update(names)

    required_exports = {
        component: sorted(set(own[component]) & needed) for component in PART_MODULES
    }
    unused_exports = {
        component: sorted(set(own[component]) - needed) for component in PART_MODULES
    }
    missing_from_parts = sorted(
        name
        for name in needed
        if name not in exported and name not in runtime_own and name not in workstream_own
        and name not in set(dir(builtins))
    )

    # After narrowing the merge to the required exports, loop 2 injects
    # ``runtime own names + required exports`` into every part module. A part is
    # only safe when each name it reads is covered by that injected set, by its
    # own bindings, or by builtins.
    injected_after_narrowing = runtime_own | {
        name for names in required_exports.values() for name in names
    }
    part_closure_gaps = {
        component: sorted(
            name
            for name in part_free[component]
            if name not in injected_after_narrowing
            and name not in own[component]
            and name not in set(dir(builtins))
        )
        for component in PART_MODULES
    }
    part_closure_gaps = {
        component: names for component, names in part_closure_gaps.items() if names
    }

    runtime_namespace_after_narrowing = injected_after_narrowing | runtime_own

    # Consumers receive the merged namespace through ``_bind`` (workstream.py) or
    # ``symbols.update(vars(workstream_commands))`` (workstream_reserve.py). The
    # merged namespace after narrowing is ``runtime own + required exports``.
    consumer_injection_gaps = {
        relative: sorted(
            name
            for name in row["free_names"]
            if name not in runtime_namespace_after_narrowing
            and name not in workstream_own
            and name not in set(dir(builtins))
        )
        for relative, row in consumers.items()
    }
    consumer_injection_gaps = {
        relative: names for relative, names in consumer_injection_gaps.items() if names
    }
    dynamic_access_gaps = sorted(
        name
        for names in attribute_accesses.values()
        for name in names
        if name not in runtime_namespace_after_narrowing
        and name not in workstream_own
        and name not in set(dir(builtins))
    )

    return {
        "schema_version": 1,
        "command": "runtime_export_audit",
        "ok": True,
        "runtime_merge_invalidated": False,
        "part_modules": list(PART_MODULES),
        "part_own_name_counts": {component: len(names) for component, names in own.items()},
        "part_own_names": own,
        "part_free_names": part_free,
        "runtime_own_top_level_count": len(runtime_own),
        "exported_name_count": len(exported),
        "collision_count": len(collisions),
        "collisions": collisions,
        "different_object_collisions": sorted(
            name for name, row in collisions.items() if not row["same_object"]
        ),
        "same_object_collisions": sorted(
            name for name, row in collisions.items() if row["same_object"]
        ),
        "consumers": consumers,
        "required_exports": required_exports,
        "required_export_counts": {
            component: len(names) for component, names in required_exports.items()
        },
        "unused_own_names": unused_exports,
        "needed_name_count": len(needed),
        "needed_names_missing_from_merge": missing_from_parts,
        "injected_after_narrowing_count": len(injected_after_narrowing),
        "part_closure_gaps": part_closure_gaps,
        "consumer_injection_gaps": consumer_injection_gaps,
        "runtime_free_names": runtime_free,
        "attribute_accesses": attribute_accesses,
        "dynamic_access_gaps": dynamic_access_gaps,
        "narrowing_is_closed": not part_closure_gaps and not dynamic_access_gaps,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--json", action="store_true", help="print the full machine-readable report")
    args = parser.parse_args(argv)

    report = collect()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    print(f"part modules: {', '.join(report['part_modules'])}")
    print(f"own top-level names per part: {report['part_own_name_counts']}")
    print(f"runtime.py own top-level names: {report['runtime_own_top_level_count']}")
    print(f"union of part exports: {report['exported_name_count']}")
    print(f"collisions: {report['collision_count']} (different object: {len(report['different_object_collisions'])})")
    for name in report["different_object_collisions"]:
        print(f"  SHADOWING {name}: {report['collisions'][name]['modules']}")
    for relative, row in report["consumers"].items():
        print(f"{relative}: {row['count']} consumed names")
        unresolved = row["not_resolvable_from_merge"]
        if unresolved:
            print(f"  NOT resolvable from the merge: {unresolved}")
    print(f"needed names (parts + consumers): {report['needed_name_count']}")
    print(f"required exports per part: {report['required_export_counts']}")
    if report["needed_names_missing_from_merge"]:
        print(f"NEEDED BUT NOT PROVIDED: {report['needed_names_missing_from_merge']}")
    print(f"injected after narrowing: {report['injected_after_narrowing_count']}")
    print(f"narrowing is closed: {report['narrowing_is_closed']}")
    for component, names in report["part_closure_gaps"].items():
        print(f"  CLOSURE GAP {component}: {names}")
    if report["dynamic_access_gaps"]:
        print(f"  DYNAMIC ACCESS GAP (tests/scripts read these off runtime/acf): {report['dynamic_access_gaps']}")
    for relative, names in report["consumer_injection_gaps"].items():
        print(f"  CONSUMER INJECTION GAP {relative}: {names}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AuditError as exc:
        print(f"runtime-export-audit failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
