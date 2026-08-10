"""Read-only context size warnings for the default active context chain."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path


DEFAULT_CONTEXT_BUDGETS: Mapping[str, tuple[int, int]] = {
    'active/Context.md': (240, 32 * 1024),
    'active/Current_Task.md': (160, 24 * 1024),
    'selected_workstream': (260, 32 * 1024),
    'selected_activity_log': (120, 16 * 1024),
}


def _measure(text: str) -> tuple[int, int]:
    return len(text.splitlines()), len(text.encode('utf-8'))


def _section_body(text: str, heading: str) -> str:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.strip() != heading:
            continue
        body: list[str] = []
        for candidate in lines[index + 1:]:
            if candidate.strip().startswith('## '):
                break
            body.append(candidate)
        return '\n'.join(body).strip('\n')
    return ''


def _warning(path: str, text: str, line_limit: int, byte_limit: int, *, kind: str) -> dict[str, object]:
    line_count, byte_count = _measure(text)
    reasons: list[str] = []
    if line_count > line_limit:
        reasons.append('lines')
    if byte_count > byte_limit:
        reasons.append('bytes')
    return {
        'kind': kind,
        'path': path,
        'line_count': line_count,
        'byte_count': byte_count,
        'line_limit': line_limit,
        'byte_limit': byte_limit,
        'reasons': reasons,
        'message': (
            f'{path} exceeds context budget: '
            f'{line_count}/{line_limit} lines, {byte_count}/{byte_limit} bytes'
        ),
    }


def _append_file_warning(
    warnings: list[dict[str, object]],
    root: Path,
    path: Path,
    line_limit: int,
    byte_limit: int,
    *,
    kind: str,
) -> None:
    if not path.is_file():
        return
    text = path.read_text(encoding='utf-8')
    line_count, byte_count = _measure(text)
    if line_count <= line_limit and byte_count <= byte_limit:
        return
    warnings.append(_warning(path.relative_to(root).as_posix(), text, line_limit, byte_limit, kind=kind))


def _selected_workstream_id(routing: Mapping[str, object] | None) -> str | None:
    if not routing:
        return None
    selected = routing.get('selected_workstream')
    if selected:
        return str(selected)
    if routing.get('context_mode') == 'global':
        return None
    # Compatibility fallback for callers constructing an older routing payload.
    entry = routing.get('recommended_entry')
    if not isinstance(entry, Mapping):
        return None
    workstream_id = entry.get('workstream_id')
    return str(workstream_id) if workstream_id else None


def context_budget_warnings(
    root: Path,
    routing: Mapping[str, object] | None = None,
) -> list[dict[str, object]]:
    """Return warnings without scanning all active Workstream content."""
    warnings: list[dict[str, object]] = []
    _append_file_warning(
        warnings, root, root / 'active' / 'Context.md', *DEFAULT_CONTEXT_BUDGETS['active/Context.md'], kind='context'
    )
    _append_file_warning(
        warnings, root, root / 'active' / 'Current_Task.md', *DEFAULT_CONTEXT_BUDGETS['active/Current_Task.md'], kind='current_task'
    )

    workstream_id = _selected_workstream_id(routing)
    if not workstream_id:
        return warnings
    detail = root / 'active' / 'workstreams' / f'{workstream_id}.md'
    _append_file_warning(
        warnings, root, detail, *DEFAULT_CONTEXT_BUDGETS['selected_workstream'], kind='selected_workstream'
    )
    if not detail.is_file():
        return warnings
    activity = _section_body(detail.read_text(encoding='utf-8'), '## Activity Log')
    if not activity:
        return warnings
    line_limit, byte_limit = DEFAULT_CONTEXT_BUDGETS['selected_activity_log']
    line_count, byte_count = _measure(activity)
    if line_count > line_limit or byte_count > byte_limit:
        warnings.append(_warning(
            f'active/workstreams/{workstream_id}.md#Activity Log',
            activity,
            line_limit,
            byte_limit,
            kind='selected_activity_log',
        ))
    return warnings
