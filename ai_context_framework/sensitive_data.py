"""Small public-boundary helpers for credential-like material.

This module deliberately does not try to classify arbitrary high-entropy
identifiers as secrets. UUIDs, Git object ids, deterministic digests and
ordinary external job ids remain valid public metadata. The helpers only
recognize explicit credential/private-key shapes and ACF authentication fields
that must not cross normal CLI/JSON/prompt/diagnostic boundaries.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any


_PRIVATE_KEY_RE = re.compile(
    r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?(?:-----END [A-Z0-9 ]*PRIVATE KEY-----|\Z)",
    re.IGNORECASE | re.DOTALL,
)
_KEYED_VALUE_START_RE = re.compile(
    r"(?ix)"
    r"(?<![\w.-])--(?P<cli_key>[A-Z][A-Z0-9_.-]*)(?:=|\s+)"
    r"|"
    r"(?<![\w.-])(?P<key_quote>[\"']?)(?P<key>[A-Z][A-Z0-9_.-]*)"
    r"(?P=key_quote)\s*[:=]\s*"
)
_BEARER_CREDENTIAL_RE = re.compile(r"(?i)\bbearer\s+[^\s,;}\]]+")
_OPENAI_STYLE_SECRET_RE = re.compile(r"\bsk-[A-Za-z0-9_-]{20,}")

# These are ACF authentication materials/verifiers, not general field-name
# heuristics. They are omitted from public structured output entirely.
_OMIT_CREDENTIAL_SEQUENCES = frozenset({("fence", "token"), ("fence", "token", "hash")})

_REDACT_CREDENTIAL_SEQUENCES = frozenset(
    {
        ("api", "key"),
        ("api", "secret"),
        ("access", "token"),
        ("refresh", "token"),
        ("bearer", "token"),
        ("private", "key"),
        ("client", "secret"),
        ("secret", "key"),
        ("secret", "access", "key"),
        ("license", "key"),
    }
)

# Provider/session token names that are unambiguously authentication material.
# Keep this list semantic and narrow: generic ``token`` / pagination /
# continuation metadata remain public unless an explicit auth/provider context
# is present.
_REDACT_PROVIDER_TOKEN_SEQUENCES = frozenset(
    {
        ("auth", "token"),
        ("id", "token"),
        ("service", "account", "token"),
        ("ci", "job", "token"),
        ("gh", "token"),
        ("node", "auth", "token"),
        ("github", "token"),
        ("gitlab", "token"),
        ("npm", "token"),
        ("pypi", "token"),
        ("vault", "token"),
        ("aws", "session", "token"),
        ("slack", "bot", "token"),
        ("slack", "app", "token"),
        ("huggingface", "token"),
        ("hf", "token"),
    }
)

_REDACT_CREDENTIAL_TERMINALS = frozenset({"password", "passwd", "authorization", "credential", "credentials"})

# Backwards-compatible public constant for callers/tests that inspect the
# canonical ACF owner-auth fields. Classification itself is semantic and uses
# ``credential_key_action`` so camelCase and namespaced keys share one rule.
PUBLIC_OMIT_KEYS = frozenset({"fence_token", "fence_token_hash"})

# Generic credential-value keys are retained structurally but their values are
# redacted. A key alone is not treated as evidence that unrelated high-entropy
# values are secret.
PUBLIC_REDACT_KEYS = frozenset(
    {
        "password",
        "passwd",
        "api_key",
        "api_secret",
        "access_token",
        "refresh_token",
        "bearer_token",
        "auth_token",
        "id_token",
        "service_account_token",
        "ci_job_token",
        "gh_token",
        "node_auth_token",
        "authorization",
        "private_key",
        "client_secret",
        "secret_key",
        "credential",
        "credentials",
        "license_key",
        "secret",
    }
)


def _key_tokens(value: object) -> tuple[str, ...]:
    text = str(value).strip()
    if not text:
        return ()
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", text)
    text = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", "_", text)
    return tuple(part.casefold() for part in re.split(r"[^A-Za-z0-9]+", text) if part)


def credential_key_action(value: object) -> str | None:
    """Classify explicit credential keys without treating generic token/license as secrets."""

    tokens = _key_tokens(value)
    if not tokens:
        return None
    for sequence in _OMIT_CREDENTIAL_SEQUENCES:
        if len(tokens) >= len(sequence) and tokens[-len(sequence) :] == sequence:
            return "omit"
    for sequence in _REDACT_CREDENTIAL_SEQUENCES:
        if len(tokens) >= len(sequence) and tokens[-len(sequence) :] == sequence:
            return "redact"
    for sequence in _REDACT_PROVIDER_TOKEN_SEQUENCES:
        if len(tokens) >= len(sequence) and tokens[-len(sequence) :] == sequence:
            return "redact"
    if tokens[-1] in _REDACT_CREDENTIAL_TERMINALS:
        return "redact"
    if tokens[-1] == "secret":
        return "redact"
    return None


def is_explicit_credential_key(value: object) -> bool:
    return credential_key_action(value) is not None


def _keyed_value_key(match: re.Match[str]) -> str:
    return str(match.group("cli_key") or match.group("key") or "")


def _has_explicit_keyed_value(value: str) -> bool:
    return any(is_explicit_credential_key(_keyed_value_key(match)) for match in _KEYED_VALUE_START_RE.finditer(value))


def _quoted_value_end(value: str, start: int) -> int | None:
    if start >= len(value) or value[start] not in {'\"', "'"}:
        return None
    quote = value[start]
    escaped = False
    for index in range(start + 1, len(value)):
        current = value[index]
        if escaped:
            escaped = False
            continue
        if current == "\\":
            escaped = True
            continue
        if current == quote:
            return index + 1
        # A quoted credential-like value may span lines (JSON/YAML diagnostics,
        # exception reprs, wrapped shell output).  Stopping at the first newline
        # would redact only the prefix and expose the remaining quoted value.
        # Continue to the closing quote; if it never arrives, fail closed by
        # redacting the remainder of the string.
    return len(value)


def _line_end(value: str, start: int) -> int:
    candidates = [index for index in (value.find("\r", start), value.find("\n", start)) if index >= 0]
    return min(candidates) if candidates else len(value)


def _unquoted_value_end(value: str, start: int) -> int:
    end = _line_end(value, start)
    next_match = _KEYED_VALUE_START_RE.search(value, start)
    if next_match is None or next_match.start() >= end:
        return end
    boundary = next_match.start()
    trimmed = boundary
    while trimmed > start and value[trimmed - 1].isspace():
        trimmed -= 1
    if trimmed > start and value[trimmed - 1] in {",", ";"}:
        trimmed -= 1
    return max(start, trimmed)


def _redact_keyed_values(value: str) -> tuple[str, int]:
    pieces: list[str] = []
    cursor = 0
    search_from = 0
    redactions = 0
    while True:
        match = _KEYED_VALUE_START_RE.search(value, search_from)
        if match is None:
            break
        key = _keyed_value_key(match)
        if not is_explicit_credential_key(key):
            search_from = match.end()
            continue
        value_start = match.end()
        value_end = _quoted_value_end(value, value_start)
        if value_end is None:
            value_end = _unquoted_value_end(value, value_start)
        pieces.append(value[cursor:value_start])
        raw_value = value[value_start:value_end]
        if len(raw_value) >= 2 and raw_value[0] in {'\"', "'"} and raw_value[-1] == raw_value[0]:
            pieces.append(f"{raw_value[0]}[redacted credential-like value]{raw_value[0]}")
        else:
            pieces.append("[redacted credential-like value]")
        redactions += 1
        cursor = value_end
        search_from = value_end
    if not redactions:
        return value, 0
    pieces.append(value[cursor:])
    return "".join(pieces), redactions


def contains_credential_like_text(value: object) -> bool:
    if not isinstance(value, str) or not value:
        return False
    return bool(
        _PRIVATE_KEY_RE.search(value)
        or _has_explicit_keyed_value(value)
        or _BEARER_CREDENTIAL_RE.search(value)
        or _OPENAI_STYLE_SECRET_RE.search(value)
    )


def redact_credential_like_text(value: str) -> tuple[str, int]:
    """Redact explicit credential shapes while preserving ordinary metadata."""

    redactions = 0

    def replace(_match: re.Match[str]) -> str:
        nonlocal redactions
        redactions += 1
        return "[redacted credential-like value]"

    text = _PRIVATE_KEY_RE.sub(replace, value)
    text, keyed_redactions = _redact_keyed_values(text)
    redactions += keyed_redactions
    text = _BEARER_CREDENTIAL_RE.sub(replace, text)
    text = _OPENAI_STYLE_SECRET_RE.sub(replace, text)
    return text, redactions


def sanitize_public_payload(value: object) -> object:
    """Remove ACF auth material and redact explicit credential-like values.

    The function intentionally preserves UUIDs, hashes/digests, generations,
    runner ids, ordinary external ids and other high-entropy metadata.
    """

    if isinstance(value, Mapping):
        cleaned: dict[str, object] = {}
        for raw_key, raw_value in value.items():
            key = str(raw_key)
            action = credential_key_action(key)
            if action == "omit":
                continue
            if action == "redact":
                cleaned[key] = "[redacted]"
            else:
                cleaned[key] = sanitize_public_payload(raw_value)
        return cleaned
    if isinstance(value, list):
        return [sanitize_public_payload(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize_public_payload(item) for item in value]
    if isinstance(value, str):
        return redact_credential_like_text(value)[0]
    return value


__all__ = [
    "PUBLIC_OMIT_KEYS",
    "credential_key_action",
    "contains_credential_like_text",
    "is_explicit_credential_key",
    "redact_credential_like_text",
    "sanitize_public_payload",
]
