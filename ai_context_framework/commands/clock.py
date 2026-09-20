"""Minute-level local clock primitive for AI-maintained context timestamps.

Context documents record fields such as “上次更新” as a local minute value
(``YYYY-MM-DD HH:MM``). Writing those by hand is a recurring drift source, so the
format is exposed here as a deterministic CLI primitive. The command deliberately
does not read or write context files and never requires a context root.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from ai_context_framework.constants import JSON_SCHEMA_VERSION
from ai_context_framework.json_contract import json_enabled, print_json


MINUTE_FORMAT = "%Y-%m-%d %H:%M"
DATE_FORMAT = "%Y-%m-%d"
TIME_FORMAT = "%H:%M"


def local_now(now: datetime | None = None) -> datetime:
    """Return an aware local datetime; ``None`` means "right now"."""

    if now is None:
        return datetime.now().astimezone()
    return now if now.tzinfo is not None else now.astimezone()


def utc_offset_value(moment: datetime) -> str:
    """Render the UTC offset as ``±HH:MM`` without depending on string slicing."""

    offset = moment.utcoffset() or timedelta(0)
    total_minutes = int(offset.total_seconds() // 60)
    sign = "-" if total_minutes < 0 else "+"
    hours, minutes = divmod(abs(total_minutes), 60)
    return f"{sign}{hours:02d}:{minutes:02d}"


def clock_now_payload(now: datetime | None = None) -> dict[str, object]:
    moment = local_now(now)
    return {
        "schema_version": JSON_SCHEMA_VERSION,
        "command": "clock now",
        "ok": True,
        "datetime": moment.strftime(MINUTE_FORMAT),
        "date": moment.strftime(DATE_FORMAT),
        "time": moment.strftime(TIME_FORMAT),
        "utc_offset": utc_offset_value(moment),
        "iso_local": moment.isoformat(timespec="seconds"),
        "utc": moment.astimezone(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
        "changed_files": [],
        "warnings": [],
        "error_code": None,
        "next_actions": [],
    }


def clock_now_command(args: argparse.Namespace, *, now: datetime | None = None) -> int:
    payload = clock_now_payload(now)
    if json_enabled(args):
        print_json(payload)
    else:
        print(payload["datetime"])
    return 0


def register_clock_parser(
    subparsers: Any,
    add_json_argument: Callable[..., None],
    *,
    now_handler: Callable[..., int],
) -> None:
    """Register the ``clock`` parser group; runtime injects the handler."""

    clock_parser = subparsers.add_parser(
        "clock", help="report local time for AI-written context timestamps"
    )
    clock_subparsers = clock_parser.add_subparsers(dest="clock_command", required=True)

    now_parser = clock_subparsers.add_parser(
        "now", help="print the current local time as YYYY-MM-DD HH:MM"
    )
    add_json_argument(now_parser)
    now_parser.set_defaults(func=now_handler)
