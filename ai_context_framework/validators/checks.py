"""Small CLI value validators and shared ID patterns."""

from __future__ import annotations

import argparse
import re
from datetime import date


DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ADR_ID_RE = re.compile(r"^ADR-(\d{4})$")
TASK_ID_RE = re.compile(r"^T(\d{3})$")
TASK_ID_TOKEN_RE = re.compile(r"\bT(\d{3})\b")
TASK_STAGE_ID_RE = re.compile(r"^T\d{3}\.\d+$")
TASK_STAGE_ID_TOKEN_RE = re.compile(r"\bT\d{3}\.\d+\b")
KNOWLEDGE_ID_RE = re.compile(r"^K(\d{3})$")
WORKSTREAM_ID_RE = re.compile(r"^WS(\d{3})$")
WORKSTREAM_ID_TOKEN_RE = re.compile(r"\bWS\d{3}\b")
WORKSTREAM_STAGE_ID_RE = re.compile(r"^WS\d{3}\.\d+$")
DRAFT_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
FEEDBACK_ID_RE = re.compile(r"^F\d{3}$")
HUMAN_NOTE_ID_RE = re.compile(r"^H\d{3}$")


def validate_date(value: str) -> str:
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid date `{value}`, expected YYYY-MM-DD") from exc
    return value


def validate_adr_id(value: str) -> str:
    if not ADR_ID_RE.match(value):
        raise argparse.ArgumentTypeError("ADR id must use ADR-0001 format")
    return value


def validate_draft_name(value: str) -> str:
    if not DRAFT_NAME_RE.match(value):
        raise argparse.ArgumentTypeError("draft name may only contain letters, digits, dot, underscore, and hyphen")
    return value


def validate_task_id(value: str) -> str:
    if not TASK_ID_RE.match(value):
        raise argparse.ArgumentTypeError("task id must use T001 format")
    return value


def validate_task_stage_id(value: str) -> str:
    if not TASK_STAGE_ID_RE.match(value):
        raise argparse.ArgumentTypeError("task stage id must use T001.1 format")
    return value


def validate_knowledge_id(value: str) -> str:
    if not KNOWLEDGE_ID_RE.match(value):
        raise argparse.ArgumentTypeError("knowledge id must use K001 format")
    return value


def validate_workstream_id(value: str) -> str:
    if not WORKSTREAM_ID_RE.match(value):
        raise argparse.ArgumentTypeError("workstream id must use WS001 format")
    return value


def validate_workstream_stage_id(value: str) -> str:
    if not WORKSTREAM_STAGE_ID_RE.match(value):
        raise argparse.ArgumentTypeError("workstream stage id must use WS001.1 format")
    return value


def validate_feedback_id(value: str) -> str:
    if not FEEDBACK_ID_RE.match(value):
        raise argparse.ArgumentTypeError(f"invalid feedback id `{value}`, expected FNNN")
    return value


def validate_human_note_id(value: str) -> str:
    if not HUMAN_NOTE_ID_RE.match(value):
        raise argparse.ArgumentTypeError(f"invalid human note id `{value}`, expected HNNN")
    return value
