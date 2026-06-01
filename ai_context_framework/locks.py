"""Filesystem lock helpers for ACF write commands."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from ai_context_framework.constants import JSON_SCHEMA_VERSION, LOCK_FILE_REL


def lock_path_for_context(root: Path) -> Path:
    return root / LOCK_FILE_REL


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def acquire_context_lock(root: Path, command: str) -> Path:
    lock_path = lock_path_for_context(root)
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise SystemExit(
            f"context is locked by another acf write command: {lock_path}; "
            "rerun after it finishes or remove the stale lock if no acf process is running"
        ) from exc
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "schema_version": JSON_SCHEMA_VERSION,
                    "command": command,
                    "created_at": _utc_now_iso(),
                    "pid": os.getpid(),
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            + "\n"
        )
    return lock_path


def release_context_lock(lock_path: Path) -> None:
    try:
        lock_path.unlink()
    except FileNotFoundError:
        return
