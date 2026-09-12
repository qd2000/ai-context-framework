"""Deterministic self-contained relationship diagrams for Observer Dashboard V2.

The renderer intentionally emits plain inline SVG with no external assets or
runtime dependencies.  It is presentation-only: node/edge semantics are
supplied by reviewed Observer authority and are never inferred here.
"""

from __future__ import annotations

from hashlib import sha256
from html import escape
from math import ceil
from typing import Callable
from unicodedata import east_asian_width


def _short_text(value: object, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if _display_width(text) <= limit:
        return text
    target = max(1, limit - 1)
    width = 0
    chars: list[str] = []
    for char in text:
        char_width = 2 if east_asian_width(char) in {"W", "F"} else 1
        if width + char_width > target:
            break
        chars.append(char)
        width += char_width
    return "".join(chars).rstrip() + "…"


def _display_width(text: str) -> int:
    return sum(2 if east_asian_width(char) in {"W", "F"} else 1 for char in text)


def _normalized_text(value: object) -> str:
    return " ".join(str(value or "").split())


def _human_status(value: object) -> str:
    raw = _normalized_text(value)
    return {
        "active": "进行中",
        "advancing": "推进中",
        "blocked": "受阻",
        "cancelled": "已取消",
        "completed": "已完成",
        "critical": "严重",
        "current": "当前",
        "failed": "失败",
        "fresh": "新鲜",
        "future": "后续阶段",
        "healthy": "健康",
        "incomplete": "未完整结束",
        "interrupted": "已中断",
        "maintenance": "维护中",
        "not_reviewed": "尚未复核",
        "partial": "部分完成",
        "planned": "待推进",
        "running": "运行中",
        "stale": "已陈旧",
        "success": "成功",
        "unconfigured": "尚未配置",
        "unknown": "未知",
        "waiting": "等待中",
        "warning": "需要关注",
    }.get(raw.casefold(), raw or "未知")


def run_source_label(value: object) -> str:
    raw = _normalized_text(value)
    return {
        "continuation_round": "Writer 持续执行轮次",
        "observer_marker": "显式自动任务运行标记",
    }.get(raw.casefold(), raw or "来源未知")


def problem_dimension_label(dimension: str, value: object) -> str:
    raw = _normalized_text(value)
    labels = {
        "handler": {
            "agent_self": "Agent 自行处理",
            "human_approval": "需要人工授权",
            "human_action": "需要人工操作",
            "external_system": "外部系统",
            "other_project": "其他项目",
        },
        "blocking_impact": {
            "non_blocking": "不阻塞",
            "degrading": "造成降级影响",
            "blocks_current_step": "阻塞当前步骤",
            "blocks_task": "阻塞整个任务",
        },
        "plan_impact": {
            "none": "无计划影响",
            "local_adjustment": "需要局部调整",
            "route_change": "需要调整路线",
            "major_replan": "需要重大重规划",
        },
        "status": {
            "detected": "已发现",
            "investigating": "调查中",
            "working": "处理中",
            "waiting": "等待中",
            "transferred": "已转交",
            "deferred": "已延期",
            "resolved": "已解决",
        },
    }
    return labels.get(dimension, {}).get(raw.casefold(), _human_status(raw) if dimension == "status" else raw or "未知")


def _human_relation_label(value: object) -> str:
    raw = _normalized_text(value)
    return {
        "next": "下一步",
        "observed_by": "由其观察",
        "depends_on": "依赖",
        "required_by": "被依赖",
        "blocks": "阻塞",
        "flows_to": "流向",
        "feeds": "输入",
        "parallel": "并行",
        "branch": "分支",
        "merge": "汇合",
    }.get(raw.casefold(), raw)


def _rectangle_edge_points(
    source: tuple[float, float],
    target: tuple[float, float],
    *,
    width: float,
    height: float,
) -> tuple[float, float, float, float]:
    """Return source/target border intersections for one center-to-center edge.

    Edge markers must terminate at the visible node border.  Ending a line at
    the target center lets the later-painted node rectangle cover the arrow
    head, which makes an otherwise structured graph look directionless.
    """

    sx, sy = source
    tx, ty = target
    dx = tx - sx
    dy = ty - sy
    if dx == 0 and dy == 0:
        return sx, sy, tx, ty

    half_w = width / 2
    half_h = height / 2
    source_scale = min(
        half_w / abs(dx) if dx else float("inf"),
        half_h / abs(dy) if dy else float("inf"),
    )
    target_scale = source_scale
    return (
        sx + dx * source_scale,
        sy + dy * source_scale,
        tx - dx * target_scale,
        ty - dy * target_scale,
    )


def render_relation_diagram(
    nodes: list[dict[str, object]],
    edges: list[dict[str, object]],
    *,
    title: str,
    problem_node_ids: set[str] | None = None,
    current_node_ids: set[str] | None = None,
    next_node_ids: set[str] | None = None,
    status_class: Callable[[object], str] | None = None,
    identity: str | None = None,
) -> str:
    """Render reviewed nodes/edges as a deterministic inline SVG graph."""

    if not nodes:
        return '<p class="muted">当前 authority 没有可绘制的关系节点。</p>'
    problem_node_ids = problem_node_ids or set()
    if current_node_ids is None:
        current_node_ids = {
            str(node.get("id"))
            for node in nodes
            if node.get("id") and str(node.get("status") or "").casefold() == "current"
        }
    else:
        current_node_ids = set(current_node_ids)
    next_node_ids = next_node_ids or set()
    tone = status_class or (lambda _value: "muted")
    marker_seed = identity or "|".join(
        [title]
        + [str(node.get("id") or "") for node in nodes]
        + [f"{edge.get('from')}->{edge.get('to')}" for edge in edges]
    )
    marker_id = f"observer-arrow-{sha256(marker_seed.encode('utf-8')).hexdigest()[:12]}"
    columns = min(4, max(1, len(nodes)))
    if len(nodes) > 4:
        columns = 3
    rows = ceil(len(nodes) / columns)
    cell_w = 250
    cell_h = 132
    margin_x = 28
    margin_y = 34
    node_w = 190
    node_h = 78
    width = margin_x * 2 + columns * cell_w
    height = margin_y * 2 + rows * cell_h
    positions: dict[str, tuple[float, float]] = {}
    node_parts: list[str] = []
    for index, node in enumerate(nodes):
        node_id = str(node.get("id") or f"node-{index}")
        col = index % columns
        row = index // columns
        x = margin_x + col * cell_w + (cell_w - node_w) / 2
        y = margin_y + row * cell_h + (cell_h - node_h) / 2
        positions[node_id] = (x, y)
        node_title = escape(_short_text(node.get("title") or node_id, 20), quote=True)
        node_status = escape(_short_text(_human_status(node.get("status")), 18), quote=True)
        node_summary = escape(_short_text(node.get("summary"), 28), quote=True)
        node_id_text = escape(_short_text(node_id, 28), quote=True)
        node_title_full = escape(_normalized_text(node.get("title") or node_id), quote=True)
        node_status_full = escape(_human_status(node.get("status")), quote=True)
        node_summary_full = escape(_normalized_text(node.get("summary")), quote=True)
        css_tone = escape(str(tone(node.get("status"))), quote=True)
        problem = node_id in problem_node_ids
        current = node_id in current_node_ids
        next_node = node_id in next_node_ids
        problem_svg = (
            f'<circle class="diagram-problem" cx="{x + node_w - 10:.1f}" cy="{y + 10:.1f}" r="10"/>'
            f'<text class="diagram-problem-text" x="{x + node_w - 10:.1f}" y="{y + 14:.1f}" text-anchor="middle">!</text>'
            if problem
            else ""
        )
        current_svg = (
            f'<rect class="diagram-current" x="{x + 8:.1f}" y="{y - 8:.1f}" width="44" height="18" rx="9"/>'
            f'<text class="diagram-current-text" x="{x + 30:.1f}" y="{y + 5:.1f}" text-anchor="middle">当前</text>'
            if current
            else ""
        )
        next_svg = (
            f'<rect class="diagram-next" x="{x + node_w - 48:.1f}" y="{y + node_h - 10:.1f}" width="40" height="18" rx="9"/>'
            f'<text class="diagram-next-text" x="{x + node_w - 28:.1f}" y="{y + node_h + 3:.1f}" text-anchor="middle">下一</text>'
            if next_node
            else ""
        )
        node_classes = ["diagram-node", f"tone-{css_tone}"]
        if current:
            node_classes.append("is-current")
        if next_node:
            node_classes.append("is-next")
        node_parts.append(
            f'<g class="{" ".join(node_classes)}" data-node-id="{escape(node_id, quote=True)}">'
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{node_w}" height="{node_h}" rx="10"/>'
            f'<text class="diagram-title" x="{x + 12:.1f}" y="{y + 22:.1f}">{node_title}</text>'
            f'<text class="diagram-status" x="{x + 12:.1f}" y="{y + 41:.1f}">{node_status}</text>'
            f'<text class="diagram-summary" x="{x + 12:.1f}" y="{y + 60:.1f}">{node_summary}</text>'
            f'<title>{node_id_text}: {node_title_full} · {node_status_full} · {node_summary_full}</title>'
            f'{current_svg}{problem_svg}{next_svg}</g>'
        )

    edge_parts: list[str] = []
    edge_list_items: list[str] = []
    for edge in edges:
        source = str(edge.get("from") or "")
        target = str(edge.get("to") or "")
        if source not in positions or target not in positions:
            continue
        sx, sy = positions[source]
        tx, ty = positions[target]
        source_center = (sx + node_w / 2, sy + node_h / 2)
        target_center = (tx + node_w / 2, ty + node_h / 2)
        x1, y1, x2, y2 = _rectangle_edge_points(
            source_center,
            target_center,
            width=node_w,
            height=node_h,
        )
        label = _short_text(_human_relation_label(edge.get("label") or edge.get("relation") or ""), 28)
        label_html = escape(label, quote=True)
        source_html = escape(source, quote=True)
        target_html = escape(target, quote=True)
        mid_x = (x1 + x2) / 2
        mid_y = (y1 + y2) / 2 - 7
        edge_parts.append(
            f'<g class="diagram-edge" data-edge-from="{source_html}" data-edge-to="{target_html}">'
            f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" marker-end="url(#{marker_id})"/>'
            f'<text x="{mid_x:.1f}" y="{mid_y:.1f}" text-anchor="middle">{label_html}</text>'
            f'<title>{source_html} → {target_html}: {label_html}</title></g>'
        )
        edge_list_items.append(f'<li><code>{source_html}</code> → <code>{target_html}</code> · {label_html}</li>')

    edge_fallback = "".join(edge_list_items) or '<li class="muted">当前没有结构化 edge；仅展示节点。</li>'
    return (
        f'<div class="relation-diagram-shell" role="group" aria-label="{escape(title, quote=True)}">'
        f'<svg class="relation-diagram" viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title, quote=True)}">'
        f'<defs><marker class="diagram-arrow" id="{marker_id}" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto" markerUnits="strokeWidth">'
        '<path d="M0,0 L8,4 L0,8 z"/></marker></defs>'
        + "".join(edge_parts)
        + "".join(node_parts)
        + '</svg><details class="diagram-edge-details"><summary>关系边文字说明</summary><ul>'
        + edge_fallback
        + "</ul></details></div>"
    )


def primary_visualization_kind_label(value: object) -> str:
    raw = _normalized_text(value)
    return {
        "metric_trend": "指标趋势",
        "status_matrix": "状态矩阵",
        "process_flow": "流程图",
        "roadmap": "推进路线",
    }.get(raw.casefold(), raw or "主可视化")


def _render_metric_trend(primary: dict[str, object]) -> str:
    spec = primary.get("spec") if isinstance(primary.get("spec"), dict) else {}
    series_rows = [row for row in spec.get("series") or [] if isinstance(row, dict)]
    all_values = [
        float(point.get("y"))
        for series in series_rows
        for point in series.get("points") or []
        if isinstance(point, dict) and isinstance(point.get("y"), (int, float))
    ]
    if not series_rows or not all_values:
        return '<p class="muted">当前没有可绘制的有限指标序列。</p>'
    y_min = min(all_values)
    y_max = max(all_values)
    if y_min == y_max:
        y_min -= 0.5
        y_max += 0.5
    width = 760
    height = 280
    left = 72
    right = 24
    top = 26
    bottom = 52
    plot_w = width - left - right
    plot_h = height - top - bottom
    max_points = max(len(series.get("points") or []) for series in series_rows)

    def point_x(index: int) -> float:
        if max_points <= 1:
            return left + plot_w / 2
        return left + plot_w * index / (max_points - 1)

    def point_y(value: float) -> float:
        return top + plot_h * (1 - (value - y_min) / (y_max - y_min))

    series_svg: list[str] = []
    legends: list[str] = []
    point_details: list[str] = []
    for series_index, series in enumerate(series_rows):
        points = [row for row in series.get("points") or [] if isinstance(row, dict)]
        coords = [
            (point_x(index), point_y(float(point.get("y"))))
            for index, point in enumerate(points)
            if isinstance(point.get("y"), (int, float))
        ]
        if not coords:
            continue
        points_attr = " ".join(f"{x:.1f},{y:.1f}" for x, y in coords)
        dash = "" if series_index == 0 else f' stroke-dasharray="{4 + series_index * 2} {3 + series_index}"'
        series_svg.append(
            f'<polyline class="trend-line trend-series-{series_index}" points="{points_attr}" '
            f'fill="none" stroke="currentColor" stroke-width="2.5"{dash}/>'
        )
        for point_index, point in enumerate(points):
            x = point_x(point_index)
            y = point_y(float(point.get("y")))
            point_label = _normalized_text(point.get("label")) or str(point.get("x"))
            series_svg.append(
                f'<circle class="trend-point trend-series-{series_index}" cx="{x:.1f}" cy="{y:.1f}" r="4" '
                'fill="currentColor">'
                f'<title>{escape(_normalized_text(series.get("title")))} · {escape(point_label)} · '
                f'{escape(str(point.get("y")))}</title></circle>'
            )
            point_details.append(
                '<li>'
                f'<strong>{escape(_normalized_text(series.get("title")))}</strong> · '
                f'{escape(point_label)} = {escape(str(point.get("y")))} '
                f'{escape(_normalized_text(series.get("unit")))}'
                '</li>'
            )
        legends.append(
            f'<span class="trend-legend-item"><strong>{escape(_normalized_text(series.get("title")))}</strong>'
            f'{(" · " + escape(_normalized_text(series.get("unit")))) if series.get("unit") else ""}</span>'
        )
    x_label = escape(_normalized_text(spec.get("x_label")))
    y_label = escape(_normalized_text(spec.get("y_label")))
    direction = {
        "minimize": "越低越好",
        "maximize": "越高越好",
        "neutral": "仅展示变化",
    }.get(str(spec.get("direction") or "neutral"), "仅展示变化")
    return (
        '<div class="primary-metric-trend">'
        f'<div class="trend-legend">{"".join(legends)}<span>{escape(direction)}</span></div>'
        f'<svg class="metric-trend-svg" viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="{escape(_normalized_text(primary.get("title")), quote=True)}">'
        f'<line x1="{left}" y1="{top + plot_h}" x2="{left + plot_w}" y2="{top + plot_h}" stroke="currentColor"/>'
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_h}" stroke="currentColor"/>'
        f'<text x="{left + plot_w / 2:.1f}" y="{height - 12}" text-anchor="middle">{x_label}</text>'
        f'<text x="18" y="{top + plot_h / 2:.1f}" text-anchor="middle" transform="rotate(-90 18 {top + plot_h / 2:.1f})">{y_label}</text>'
        f'<text x="{left - 8}" y="{top + 5}" text-anchor="end">{escape(f"{y_max:g}")}</text>'
        f'<text x="{left - 8}" y="{top + plot_h}" text-anchor="end">{escape(f"{y_min:g}")}</text>'
        + "".join(series_svg)
        + '</svg><details class="primary-visualization-data"><summary>查看指标点明细</summary><ul>'
        + "".join(point_details)
        + '</ul></details></div>'
    )


def _render_status_matrix(primary: dict[str, object]) -> str:
    spec = primary.get("spec") if isinstance(primary.get("spec"), dict) else {}
    items = [row for row in spec.get("items") or [] if isinstance(row, dict)]
    current_refs = {str(item) for item in spec.get("current_item_refs") or []}
    if not items:
        return '<p class="muted">当前没有可展示的状态矩阵项。</p>'
    cards: list[str] = []
    for row in items:
        item_id = str(row.get("id") or "")
        current = item_id in current_refs
        evidence = [str(item) for item in row.get("evidence_refs") or []]
        cards.append(
            f'<details class="status-matrix-item {"is-current" if current else ""}" '
            f'data-matrix-item="{escape(item_id, quote=True)}">'
            '<summary>'
            f'<strong>{escape(_normalized_text(row.get("title")))}</strong>'
            f'<span>{escape(_human_status(row.get("status")))}</span>'
            f'{"<em>当前</em>" if current else ""}'
            '</summary>'
            f'<p>{escape(_normalized_text(row.get("summary")))}</p>'
            '<div class="muted">证据：'
            + (" · ".join(f'<code>{escape(ref)}</code>' for ref in evidence) if evidence else "无")
            + '</div></details>'
        )
    return '<div class="status-matrix" role="list">' + "".join(cards) + '</div>'


def render_primary_visualization(
    primary: dict[str, object],
    *,
    status_class: Callable[[object], str] | None = None,
    identity: str | None = None,
) -> str:
    """Render one validated task-semantic primary visualization.

    Selection is intentionally outside this renderer.  The caller supplies a
    reviewed structured spec; this function only deterministically projects
    that spec and never inspects project/target names to choose a kind.
    """

    kind = str(primary.get("kind") or "")
    spec = primary.get("spec") if isinstance(primary.get("spec"), dict) else {}
    confidence = str(primary.get("confidence") or "")
    if kind == "metric_trend":
        body = _render_metric_trend(primary)
    elif kind == "status_matrix":
        body = _render_status_matrix(primary)
    elif kind in {"process_flow", "roadmap"}:
        nodes = [row for row in spec.get("nodes") or [] if isinstance(row, dict)]
        edges = [row for row in spec.get("edges") or [] if isinstance(row, dict)]
        body = render_relation_diagram(
            nodes,
            edges,
            title=_normalized_text(primary.get("title")) or primary_visualization_kind_label(kind),
            current_node_ids={str(item) for item in spec.get("current_node_refs") or []} or None,
            next_node_ids={str(item) for item in spec.get("next_node_refs") or []},
            status_class=status_class,
            identity=identity,
        )
    else:
        return '<p class="muted">当前主可视化类型无法渲染。</p>'
    low_confidence = (
        '<div class="semantic-notice tone-border-warning"><strong>低置信可视化</strong>'
        '<p>当前主图选择证据有限；请结合来源与后续语义复核阅读。</p></div>'
        if confidence == "low"
        else ""
    )
    return (
        '<section class="primary-visualization" '
        f'data-primary-visualization-kind="{escape(kind, quote=True)}">'
        '<div class="primary-visualization-heading">'
        f'<div><span class="target-eyebrow">核心进展问题</span><h4>{escape(_normalized_text(primary.get("primary_progress_question")))}</h4></div>'
        f'<span class="badge tone-active">{escape(primary_visualization_kind_label(kind))}</span></div>'
        f'<p class="primary-visualization-reason">{escape(_normalized_text(primary.get("reason")))}</p>'
        f'{low_confidence}{body}'
        '</section>'
    )


def render_target_execution_summary(
    view: dict[str, object],
    alerts: list[dict[str, object]],
    *,
    display_time: Callable[[object], str],
) -> str:
    """Render a compact progress strip above the map-first target view."""

    latest = view.get("latest_run") if isinstance(view.get("latest_run"), dict) else None
    semantic = view.get("semantic_review") if isinstance(view.get("semantic_review"), dict) else {}
    review = semantic.get("current_review") if isinstance(semantic.get("current_review"), dict) else {}
    narrative = review.get("narrative") if isinstance(review.get("narrative"), dict) else {}
    route_nodes = [row for row in narrative.get("route_nodes") or [] if isinstance(row, dict)]
    completed = sum(1 for row in route_nodes if str(row.get("status") or "").casefold() == "completed")
    total = len(route_nodes)
    progress_text = f"{completed}/{total} 个路线节点已完成" if total else "尚无可计数路线节点"
    workstreams = [row for row in view.get("workstreams") or [] if isinstance(row, dict)]
    health_values = [
        str((row.get("machine_state") or {}).get("health") or "unknown")
        for row in workstreams
        if isinstance(row.get("machine_state"), dict)
    ]
    if any(value == "critical" for value in health_values):
        health = "严重"
    elif alerts or any(value == "warning" for value in health_values):
        health = "需要关注"
    elif health_values and all(value == "healthy" for value in health_values):
        health = "健康"
    else:
        health = "尚未判定"
    human_alerts = [
        row
        for row in alerts
        if isinstance(row, dict)
        and (
            (row.get("handler") in {"human_approval", "human_action"})
            or "human" in str(row.get("explanation") or "").casefold()
        )
    ]
    human_text = "需要人工介入" if human_alerts else "当前无明确人工介入要求"
    if latest is None:
        latest_result = "尚无可归属运行"
        latest_outcome = "暂无最近实质进展"
    else:
        latest_result = _human_status(latest.get("result") or latest.get("status") or "unknown")
        latest_outcome = _normalized_text(latest.get("major_outcome")) or "暂无主要产出"
    return (
        '<section class="target-map-summary" aria-label="路线进度摘要">'
        f'<div class="target-map-metric"><span>路线进度</span><strong>{escape(progress_text)}</strong></div>'
        f'<div class="target-map-metric"><span>执行健康</span><strong>{escape(health)}</strong><small>{escape(human_text)}</small></div>'
        '<div class="target-latest-outcome">'
        f'<span>最近实质进展 · {escape(str(latest_result))}</span><strong>{escape(latest_outcome)}</strong>'
        '</div>'
        "</section>"
    )


def render_target_run_history(
    runs: object,
    *,
    display_time: Callable[[object], str],
) -> str:
    """Render attributable Agent runs as a compact table with folded details."""

    rows = [row for row in runs or [] if isinstance(row, dict)] if isinstance(runs, list) else []
    if not rows:
        return '<p class="muted">暂无可归属到该已注册自动任务的运行记录。</p>'

    def duration_text(row: dict[str, object]) -> str:
        duration = row.get("duration_seconds")
        lower_bound = row.get("lower_bound_duration_seconds")
        if isinstance(duration, (int, float)):
            return f"{duration:.1f}s"
        if isinstance(lower_bound, (int, float)):
            return f"≥ {lower_bound:.1f}s（下界）"
        return "未知"

    def row_html(row: dict[str, object]) -> str:
        result = _human_status(row.get("result") or row.get("status") or "unknown")
        outcome = _normalized_text(row.get("major_outcome")) or "—"
        route_ref = _normalized_text(row.get("route_ref")) or "—"
        evidence_refs = [_normalized_text(item) for item in row.get("evidence_refs") or [] if _normalized_text(item)]
        provenance = [f"来源：{run_source_label(row.get('source'))}"] if row.get("source") else []
        if row.get("generation") is not None:
            provenance.append(f"generation {row.get('generation')}")
        if row.get("runner_id"):
            provenance.append(f"runner {row.get('runner_id')}")
        detail_parts = [
            f'<div>run：<code>{escape(_normalized_text(row.get("run_id")) or "—")}</code></div>',
            f'<div>最后活动：{escape(display_time(row.get("last_activity_at")))}</div>',
            f'<div>{escape(" · ".join(provenance) or "来源未知")}</div>',
            f'<div>证据覆盖：{len(evidence_refs)} 条</div>',
        ]
        if evidence_refs:
            detail_parts.append(
                '<div class="run-evidence-list">'
                + "".join(f'<code>{escape(ref)}</code>' for ref in evidence_refs)
                + '</div>'
            )
        else:
            detail_parts.append('<div class="muted">尚无可归属 evidence_ref</div>')
        details = '<details class="target-run-technical"><summary>详情</summary>' + "".join(detail_parts) + '</details>'
        return (
            '<tr class="target-run-row">'
            f'<td><time>{escape(display_time(row.get("started_at")))}</time></td>'
            f'<td>{escape(duration_text(row))}</td>'
            f'<td><strong>{escape(result)}</strong></td>'
            f'<td class="target-run-outcome">{escape(outcome)}</td>'
            f'<td><code>{escape(route_ref)}</code></td>'
            f'<td>{details}</td>'
            '</tr>'
        )

    visible_limit = 6
    visible_rows = list(reversed(rows[-visible_limit:]))
    older_rows = list(reversed(rows[:-visible_limit]))
    table_head = '<thead><tr><th>开始时间</th><th>时长</th><th>结果</th><th>主要产出</th><th>路线关联</th><th></th></tr></thead>'
    visible_table = (
        '<div class="target-run-table-wrap"><table class="target-run-table">'
        + table_head
        + '<tbody>'
        + "".join(row_html(row) for row in visible_rows)
        + '</tbody></table></div>'
    )
    if not older_rows:
        return visible_table
    older_table = (
        '<div class="target-run-table-wrap"><table class="target-run-table">'
        + table_head
        + '<tbody>'
        + "".join(row_html(row) for row in older_rows)
        + '</tbody></table></div>'
    )
    return (
        f'<p class="muted run-history-summary">共 {len(rows)} 次可归属运行；默认显示最近 {len(visible_rows)} 次。</p>'
        + visible_table
        + '<details class="target-run-history-archive">'
        + f'<summary>查看更早 {len(older_rows)} 次运行</summary>'
        + older_table
        + '</details>'
    )
