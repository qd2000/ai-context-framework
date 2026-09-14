"""Exception-atomic helpers for bounded Continuation multi-file commits.

Continuation state is intentionally plain JSON rather than a database.  A
single owner transition can still touch several JSON files, so a Python-level
write failure must not leave a partially advanced generation behind.  This
module snapshots the exact pre-call bytes/existence of the bounded target set
and can restore them with independent low-level atomic writes.

This protects ordinary exceptions/fault injection.  It is not a claim of
cross-file crash atomicity across sudden process or machine loss; existing
reconcile/recovery evidence remains authoritative for abnormal termination.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


class ContinuationTransactionError(RuntimeError):
    """A bounded rollback could not restore every target."""

    def __init__(self, failures: list[str]) -> None:
        super().__init__("continuation transaction rollback failed")
        self.failures = failures


@dataclass(frozen=True)
class FileSnapshot:
    path: Path
    existed: bool
    content: bytes | None


def snapshot_paths(paths: Iterable[Path]) -> list[FileSnapshot]:
    snapshots: list[FileSnapshot] = []
    seen: set[Path] = set()
    for raw_path in paths:
        path = Path(raw_path)
        if path in seen:
            continue
        seen.add(path)
        try:
            content = path.read_bytes()
        except FileNotFoundError:
            snapshots.append(FileSnapshot(path=path, existed=False, content=None))
        else:
            snapshots.append(FileSnapshot(path=path, existed=True, content=content))
    return snapshots


def _atomic_write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.rollback-{os.getpid()}-{time.time_ns()}")
    try:
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0)
        fd = os.open(temp_path, flags, 0o600)
        try:
            view = memoryview(content)
            while view:
                written = os.write(fd, view)
                if written <= 0:  # pragma: no cover - defensive OS boundary
                    raise OSError("rollback write made no progress")
                view = view[written:]
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(temp_path, path)
    finally:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass


def restore_paths(snapshots: Iterable[FileSnapshot]) -> None:
    failures: list[str] = []
    for snapshot in reversed(list(snapshots)):
        try:
            if snapshot.existed:
                assert snapshot.content is not None
                _atomic_write_bytes(snapshot.path, snapshot.content)
            else:
                snapshot.path.unlink(missing_ok=True)
        except OSError:
            failures.append(str(snapshot.path))
    if failures:
        raise ContinuationTransactionError(failures)


__all__ = [
    "ContinuationTransactionError",
    "FileSnapshot",
    "restore_paths",
    "snapshot_paths",
]
