"""Local capability files for Continuation owner authentication.

The public CLI passes only an opaque local path.  Reusable authentication
material remains inside the file and is loaded only by the ACF process that is
about to verify the active lease.  The file is deliberately separate from the
canonical Continuation state: ``lease.json`` continues to store only the
credential verifier.
"""

from __future__ import annotations

import json
import hashlib
import hmac
import os
import re
import secrets
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

OWNER_CONTEXT_SCHEMA = "acf.continuation.owner-context.v1"
OWNER_CONTEXT_DIRECTORY = "owner_contexts"
MAX_OWNER_CONTEXT_BYTES = 16 * 1024
MAX_LEGACY_CREDENTIAL_BYTES = 4096
_CONTEXT_ID_RE = re.compile(r"ctx-[0-9a-f]{32}")
_CREDENTIAL_RE = re.compile(r"[0-9a-f]{64}")


class OwnerContextError(ValueError):
    """A local owner capability is unavailable, invalid, or misbound."""

    def __init__(self, message: str, *, code: str = "owner_context_invalid") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class OwnerContext:
    handle: Path
    context_id: str
    workspace_root: str
    task_id: str
    lease_id: str
    generation: int
    runner_id: str
    credential: str
    created_at: str

    def public_handle(self) -> dict[str, Any]:
        return {
            "schema_version": OWNER_CONTEXT_SCHEMA,
            "handle": str(self.handle),
            "context_id": self.context_id,
            "transport": "local_file",
        }


def owner_context_directory(task_directory: Path) -> Path:
    return task_directory / OWNER_CONTEXT_DIRECTORY


def _resolved(path: Path) -> Path:
    return path.expanduser().resolve()


def _is_reparse_or_link(path: Path) -> bool:
    try:
        if path.is_symlink():
            return True
        is_junction = getattr(path, "is_junction", None)
        if callable(is_junction) and is_junction():
            return True
        metadata = path.lstat()
    except (OSError, RuntimeError):
        return False
    attributes = int(getattr(metadata, "st_file_attributes", 0) or 0)
    reparse_flag = int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
    return bool(attributes & reparse_flag)


def _validate_context_directory(task_directory: Path, *, create: bool) -> Path:
    directory = owner_context_directory(task_directory).expanduser()
    created_here = False
    if directory.exists() or directory.is_symlink():
        if _is_reparse_or_link(directory):
            raise OwnerContextError(
                "owner context directory cannot be a symbolic link, junction, or reparse point",
                code="owner_context_binding_mismatch",
            )
        if not directory.is_dir():
            raise OwnerContextError(
                "owner context directory is not a directory",
                code="owner_context_unavailable",
            )
    elif create:
        try:
            directory.mkdir(parents=True, exist_ok=False, mode=0o700)
            created_here = True
        except FileExistsError:
            return _validate_context_directory(task_directory, create=False)
        except OSError as exc:
            raise OwnerContextError(
                "owner context directory could not be created",
                code="owner_context_unavailable",
            ) from exc
    else:
        raise OwnerContextError(
            "owner context directory is unavailable",
            code="owner_context_unavailable",
        )

    if _is_reparse_or_link(directory):
        raise OwnerContextError(
            "owner context directory cannot be a symbolic link, junction, or reparse point",
            code="owner_context_binding_mismatch",
        )
    try:
        if os.name != "nt":
            if created_here:
                os.chmod(directory, 0o700)
            metadata = directory.stat()
            if stat.S_IMODE(metadata.st_mode) & 0o077:
                raise OwnerContextError(
                    "owner context directory permissions are not private",
                    code="owner_context_unavailable",
                )
            getuid = getattr(os, "getuid", None)
            if callable(getuid) and metadata.st_uid != getuid():
                raise OwnerContextError(
                    "owner context directory owner does not match the current user",
                    code="owner_context_binding_mismatch",
                )
    except OwnerContextError:
        raise
    except OSError as exc:
        raise OwnerContextError(
            "owner context directory could not be validated",
            code="owner_context_unavailable",
        ) from exc
    # Windows does not expose a portable stdlib ACL proof.  We reject reparse
    # redirection and non-regular capability files but do not claim that chmod
    # proves an owner-only ACL on that platform.
    return directory


def _validate_payload(payload: Mapping[str, Any], *, handle: Path) -> OwnerContext:
    required = {
        "schema_version",
        "context_id",
        "workspace_root",
        "task_id",
        "lease_id",
        "generation",
        "runner_id",
        "credential",
        "created_at",
    }
    if payload.get("schema_version") != OWNER_CONTEXT_SCHEMA or set(payload) != required:
        raise OwnerContextError("owner context schema is invalid")

    context_id = payload.get("context_id")
    if not isinstance(context_id, str) or not _CONTEXT_ID_RE.fullmatch(context_id):
        raise OwnerContextError("owner context id is invalid")
    for field in ("workspace_root", "task_id", "lease_id", "runner_id", "created_at"):
        value = payload.get(field)
        if not isinstance(value, str) or not value.strip():
            raise OwnerContextError(f"owner context field is invalid: {field}")
    generation = payload.get("generation")
    if isinstance(generation, bool) or not isinstance(generation, int) or generation < 1:
        raise OwnerContextError("owner context generation is invalid")
    credential = payload.get("credential")
    if not isinstance(credential, str) or not _CREDENTIAL_RE.fullmatch(credential):
        raise OwnerContextError("owner context authentication material is invalid")
    if handle.name != f"{context_id}.json":
        raise OwnerContextError("owner context handle does not match its context id")
    return OwnerContext(
        handle=handle,
        context_id=context_id,
        workspace_root=str(payload["workspace_root"]),
        task_id=str(payload["task_id"]),
        lease_id=str(payload["lease_id"]),
        generation=generation,
        runner_id=str(payload["runner_id"]),
        credential=credential,
        created_at=str(payload["created_at"]),
    )


def create_owner_context(
    task_directory: Path,
    *,
    workspace_root: Path,
    task_id: str,
    lease_id: str,
    generation: int,
    runner_id: str,
    credential: str,
    created_at: str,
) -> OwnerContext:
    """Create a restricted local owner context before owner state is committed."""

    directory = _validate_context_directory(task_directory, create=True)

    serialized: str | None = None
    handle: Path | None = None
    payload: dict[str, Any] | None = None
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    flags |= getattr(os, "O_BINARY", 0)
    flags |= getattr(os, "O_NOINHERIT", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    for _attempt in range(8):
        context_id = f"ctx-{secrets.token_hex(16)}"
        candidate = directory / f"{context_id}.json"
        payload = {
            "schema_version": OWNER_CONTEXT_SCHEMA,
            "context_id": context_id,
            "workspace_root": str(_resolved(workspace_root)),
            "task_id": task_id,
            "lease_id": lease_id,
            "generation": generation,
            "runner_id": runner_id,
            "credential": credential,
            "created_at": created_at,
        }
        _validate_payload(payload, handle=candidate)
        serialized = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ) + "\n"
        try:
            fd = os.open(candidate, flags, 0o600)
        except FileExistsError:
            continue
        except OSError as exc:
            raise OwnerContextError(
                "owner context could not be created",
                code="owner_context_unavailable",
            ) from exc
        handle = candidate
        try:
            metadata = os.fstat(fd)
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
                raise OSError("owner context is not a single-link regular file")
            if os.name != "nt":
                if stat.S_IMODE(metadata.st_mode) & 0o077:
                    raise OSError("owner context permissions are not private")
                getuid = getattr(os, "getuid", None)
                if callable(getuid) and metadata.st_uid != getuid():
                    raise OSError("owner context owner does not match the current user")
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
                fd = -1
                stream.write(serialized)
                stream.flush()
                os.fsync(stream.fileno())
            if os.name != "nt":
                os.chmod(handle, 0o600)
        except OSError as exc:
            if fd >= 0:
                os.close(fd)
            handle.unlink(missing_ok=True)
            raise OwnerContextError(
                "owner context could not be created",
                code="owner_context_unavailable",
            ) from exc
        break
    else:  # pragma: no cover - cryptographic collision defense
        raise OwnerContextError(
            "could not allocate a unique owner context handle",
            code="owner_context_unavailable",
        )
    assert handle is not None and payload is not None and serialized is not None
    return _validate_payload(payload, handle=handle)


def load_owner_context(
    raw_handle: str | Path,
    task_directory: Path,
    *,
    workspace_root: Path,
    task_id: str,
) -> OwnerContext:
    """Load and bind-check one ACF-issued owner capability file."""

    value = str(raw_handle).strip()
    if not value:
        raise OwnerContextError("owner context handle is required", code="owner_context_required")
    expected_directory = _resolved(_validate_context_directory(task_directory, create=False))
    unresolved_handle = Path(value).expanduser()
    try:
        if _is_reparse_or_link(unresolved_handle):
            raise OwnerContextError(
                "owner context handle cannot be a symbolic link, junction, or reparse point",
                code="owner_context_binding_mismatch",
            )
        handle = _resolved(unresolved_handle)
    except OwnerContextError:
        raise
    except (OSError, RuntimeError) as exc:
        raise OwnerContextError(
            "owner context handle is unavailable",
            code="owner_context_unavailable",
        ) from exc
    if handle.parent != expected_directory:
        raise OwnerContextError(
            "owner context handle is outside the configured task capability directory",
            code="owner_context_binding_mismatch",
        )
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOINHERIT", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    fd = -1
    try:
        fd = os.open(handle, flags)
        metadata = os.fstat(fd)
        if not stat.S_ISREG(metadata.st_mode):
            raise OwnerContextError(
                "owner context handle is not a regular file",
                code="owner_context_binding_mismatch",
            )
        if metadata.st_nlink != 1:
            raise OwnerContextError(
                "owner context handle has an invalid link count",
                code="owner_context_binding_mismatch",
            )
        if metadata.st_size < 2 or metadata.st_size > MAX_OWNER_CONTEXT_BYTES:
            raise OwnerContextError("owner context size is invalid")
        if os.name != "nt":
            if stat.S_IMODE(metadata.st_mode) & 0o077:
                raise OwnerContextError(
                    "owner context permissions are not private",
                    code="owner_context_binding_mismatch",
                )
            getuid = getattr(os, "getuid", None)
            if callable(getuid) and metadata.st_uid != getuid():
                raise OwnerContextError(
                    "owner context owner does not match the current user",
                    code="owner_context_binding_mismatch",
                )
        chunks: list[bytes] = []
        remaining = MAX_OWNER_CONTEXT_BYTES + 1
        while remaining > 0:
            chunk = os.read(fd, min(4096, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw_bytes = b"".join(chunks)
        if len(raw_bytes) > MAX_OWNER_CONTEXT_BYTES:
            raise OwnerContextError("owner context size is invalid")
        raw = raw_bytes.decode("utf-8")
        payload = json.loads(raw)
    except OwnerContextError:
        raise
    except FileNotFoundError as exc:
        raise OwnerContextError(
            "owner context handle is unavailable",
            code="owner_context_unavailable",
        ) from exc
    except PermissionError as exc:
        raise OwnerContextError(
            "owner context handle is unavailable",
            code="owner_context_unavailable",
        ) from exc
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise OwnerContextError("owner context could not be read or parsed") from exc
    finally:
        if fd >= 0:
            os.close(fd)
    if not isinstance(payload, Mapping):
        raise OwnerContextError("owner context payload is invalid")
    context = _validate_payload(payload, handle=handle)
    if _resolved(Path(context.workspace_root)) != _resolved(workspace_root):
        raise OwnerContextError(
            "owner context workspace binding does not match this command",
            code="owner_context_binding_mismatch",
        )
    if context.task_id != task_id:
        raise OwnerContextError(
            "owner context task binding does not match this command",
            code="owner_context_binding_mismatch",
        )
    return context


def _load_legacy_credential_file(raw_handle: str | Path) -> tuple[Path, str, tuple[int, int, int]]:
    """Read one retired token-file credential without exposing it publicly."""

    value = str(raw_handle).strip()
    if not value:
        raise OwnerContextError(
            "legacy owner credential file is required",
            code="legacy_owner_transport_unavailable",
        )
    unresolved = Path(value).expanduser()
    try:
        if _is_reparse_or_link(unresolved):
            raise OwnerContextError(
                "legacy owner credential file cannot be a link or reparse point",
                code="legacy_owner_transport_invalid",
            )
        handle = _resolved(unresolved)
    except OwnerContextError:
        raise
    except (OSError, RuntimeError) as exc:
        raise OwnerContextError(
            "legacy owner credential file is unavailable",
            code="legacy_owner_transport_unavailable",
        ) from exc

    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOINHERIT", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    fd = -1
    try:
        fd = os.open(handle, flags)
        metadata = os.fstat(fd)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise OwnerContextError(
                "legacy owner credential file is not a single-link regular file",
                code="legacy_owner_transport_invalid",
            )
        if metadata.st_size < 1 or metadata.st_size > MAX_LEGACY_CREDENTIAL_BYTES:
            raise OwnerContextError(
                "legacy owner credential file size is invalid",
                code="legacy_owner_transport_invalid",
            )
        if os.name != "nt":
            if stat.S_IMODE(metadata.st_mode) & 0o077:
                raise OwnerContextError(
                    "legacy owner credential file permissions are not private",
                    code="legacy_owner_transport_invalid",
                )
            getuid = getattr(os, "getuid", None)
            if callable(getuid) and metadata.st_uid != getuid():
                raise OwnerContextError(
                    "legacy owner credential file owner does not match the current user",
                    code="legacy_owner_transport_invalid",
                )
        chunks: list[bytes] = []
        remaining = MAX_LEGACY_CREDENTIAL_BYTES + 1
        while remaining > 0:
            chunk = os.read(fd, min(4096, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        if len(raw) > MAX_LEGACY_CREDENTIAL_BYTES:
            raise OwnerContextError(
                "legacy owner credential file size is invalid",
                code="legacy_owner_transport_invalid",
            )
        credential = raw.decode("utf-8").strip()
    except OwnerContextError:
        raise
    except FileNotFoundError as exc:
        raise OwnerContextError(
            "legacy owner credential file is unavailable",
            code="legacy_owner_transport_unavailable",
        ) from exc
    except PermissionError as exc:
        raise OwnerContextError(
            "legacy owner credential file is unavailable",
            code="legacy_owner_transport_unavailable",
        ) from exc
    except (OSError, UnicodeError) as exc:
        raise OwnerContextError(
            "legacy owner credential file could not be read",
            code="legacy_owner_transport_invalid",
        ) from exc
    finally:
        if fd >= 0:
            os.close(fd)
    if not _CREDENTIAL_RE.fullmatch(credential):
        raise OwnerContextError(
            "legacy owner credential file does not contain a valid owner credential",
            code="legacy_owner_transport_invalid",
        )
    return handle, credential, (int(metadata.st_dev), int(metadata.st_ino), int(metadata.st_size))


def migrate_legacy_token_file(
    task_directory: Path,
    *,
    legacy_token_file: str | Path,
    workspace_root: Path,
    task_id: str,
    lease_id: str,
    generation: int,
    runner_id: str,
    credential_verifier: str,
    created_at: str,
) -> OwnerContext:
    """Convert a pre-.90 local token file into the current owner capability.

    The active lease and generation are not changed.  The retired file path is
    only a local input handle; its reusable credential is read in-process,
    verified against the durable lease verifier, and never returned.
    """

    legacy_handle, credential, identity = _load_legacy_credential_file(legacy_token_file)
    actual_verifier = hashlib.sha256(credential.encode("utf-8")).hexdigest()
    if not hmac.compare_digest(str(credential_verifier), actual_verifier):
        raise OwnerContextError(
            "legacy owner credential does not authenticate the active lease",
            code="legacy_owner_transport_mismatch",
        )

    context = create_owner_context(
        task_directory,
        workspace_root=workspace_root,
        task_id=task_id,
        lease_id=lease_id,
        generation=generation,
        runner_id=runner_id,
        credential=credential,
        created_at=created_at,
    )
    try:
        current = legacy_handle.lstat()
        current_identity = (int(current.st_dev), int(current.st_ino), int(current.st_size))
        if current_identity != identity or _is_reparse_or_link(legacy_handle):
            raise OSError("legacy owner credential file changed during migration")
        legacy_handle.unlink()
    except OSError as exc:
        revoked = revoke_owner_context(context, task_directory)
        if not revoked:
            raise OwnerContextError(
                "legacy owner migration cleanup and rollback were incomplete",
                code="owner_context_migration_rollback_failed",
            ) from exc
        raise OwnerContextError(
            "legacy owner credential file could not be retired; migration was rolled back",
            code="owner_context_migration_cleanup_failed",
        ) from exc
    return context


def revoke_owner_context(context: OwnerContext | Path | str, task_directory: Path) -> bool:
    """Best-effort removal of one exact task-local owner context."""

    handle = context.handle if isinstance(context, OwnerContext) else Path(context)
    try:
        directory = _validate_context_directory(task_directory, create=False)
        expected_directory = _resolved(directory)
        candidate = handle.expanduser()
        if _resolved(candidate.parent) != expected_directory:
            return False
        candidate.unlink(missing_ok=True)
        return not candidate.exists()
    except (OSError, RuntimeError, OwnerContextError):
        return False


def revoke_other_owner_contexts(task_directory: Path, *, keep: Path) -> int:
    """Remove stale task-local contexts after a new generation is committed."""

    try:
        directory = _validate_context_directory(task_directory, create=False)
    except OwnerContextError:
        return 0
    try:
        keep_resolved = _resolved(keep)
    except (OSError, RuntimeError):
        return 0
    removed = 0
    try:
        candidates = list(directory.glob("ctx-*.json"))
    except OSError:
        return 0
    for candidate in candidates:
        try:
            if _resolved(candidate) == keep_resolved:
                continue
        except (OSError, RuntimeError):
            continue
        if revoke_owner_context(candidate, task_directory):
            removed += 1
    return removed


def inspect_owner_context_transport(
    task_directory: Path,
    *,
    workspace_root: Path,
    task_id: str,
    lease_id: str,
    generation: int,
    runner_id: str,
    credential_verifier: str,
) -> dict[str, Any]:
    """Project whether the active lease has a usable current owner capability."""

    directory = owner_context_directory(task_directory)
    if not directory.exists() and not directory.is_symlink():
        return {"state": "absent", "migration_required": True}
    try:
        validated_directory = _validate_context_directory(task_directory, create=False)
        candidates = list(validated_directory.glob("ctx-*.json"))
    except (OwnerContextError, OSError) as exc:
        return {
            "state": "invalid",
            "migration_required": True,
            "reason": str(exc),
        }

    invalid_count = 0
    for candidate in candidates:
        try:
            context = load_owner_context(
                candidate,
                task_directory,
                workspace_root=workspace_root,
                task_id=task_id,
            )
        except OwnerContextError:
            invalid_count += 1
            continue
        if (
            context.lease_id != lease_id
            or context.generation != generation
            or context.runner_id != runner_id
        ):
            continue
        actual_verifier = hashlib.sha256(context.credential.encode("utf-8")).hexdigest()
        if hmac.compare_digest(credential_verifier, actual_verifier):
            return {
                "state": "current",
                "migration_required": False,
                "context_id": context.context_id,
            }
        invalid_count += 1
    return {
        "state": "invalid" if invalid_count else "absent",
        "migration_required": True,
        "invalid_context_count": invalid_count,
    }


__all__ = [
    "MAX_LEGACY_CREDENTIAL_BYTES",
    "MAX_OWNER_CONTEXT_BYTES",
    "OWNER_CONTEXT_DIRECTORY",
    "OWNER_CONTEXT_SCHEMA",
    "OwnerContext",
    "OwnerContextError",
    "create_owner_context",
    "load_owner_context",
    "migrate_legacy_token_file",
    "inspect_owner_context_transport",
    "owner_context_directory",
    "revoke_other_owner_contexts",
    "revoke_owner_context",
]
