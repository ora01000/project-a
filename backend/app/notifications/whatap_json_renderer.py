"""Render ``whatap-json`` time-series fences as chart images for HTML email."""

from __future__ import annotations

import base64
import json
import logging
import math
import re
import shutil
import subprocess
from datetime import datetime
from typing import Any
from xml.sax.saxutils import escape

logger = logging.getLogger(__name__)

WHATAP_FENCE_PATTERN = re.compile(
    r"```(?:whatap-json|whatap)\s*\r?\n(.*?)```",
    re.DOTALL | re.IGNORECASE,
)

_PLAIN_CHART_PLACEHOLDER = "[Whatap 성능 차트]"

# Always light theme — independent of app dark/light UI.
_SERIES_COLORS = (
    "#0284c7",
    "#059669",
    "#d97706",
    "#e11d48",
    "#65a30d",
    "#0891b2",
    "#ea580c",
    "#c026d3",
)
_THEME = {
    "background": "#ffffff",
    "plot_fill": "#f8fafc",
    "plot_stroke": "#e2e8f0",
    "grid": "#e2e8f0",
    "title": "#0f172a",
    "subtitle": "#64748b",
    "axis_label": "#64748b",
    "legend": "#334155",
}


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _parse_point(raw: Any) -> tuple[str, float] | None:
    if isinstance(raw, (list, tuple)) and len(raw) >= 2:
        t, v = raw[0], raw[1]
        if t is None or not _is_number(v):
            return None
        return str(t), float(v)
    if isinstance(raw, dict):
        t = raw.get("t", raw.get("time", raw.get("ts", raw.get("timestamp"))))
        v = raw.get("v", raw.get("value", raw.get("y")))
        if t is None or not _is_number(v):
            return None
        return str(t), float(v)
    return None


def is_whatap_json_chart(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    series = value.get("series")
    if not isinstance(series, list) or not series:
        return False
    for item in series:
        if not isinstance(item, dict):
            return False
        points = item.get("points")
        if not isinstance(points, list) or not points:
            return False
        if any(_parse_point(point) is None for point in points):
            return False
    return True


def parse_whatap_json(text: str) -> dict[str, Any] | None:
    trimmed = (text or "").strip()
    if not trimmed:
        return None
    try:
        parsed = json.loads(trimmed)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    return parsed if is_whatap_json_chart(parsed) else None


def _parse_time_ms(value: str) -> float | None:
    text = (value or "").strip()
    if not text:
        return None
    try:
        # Support trailing Z and offset forms.
        normalized = text.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized).timestamp() * 1000.0
    except ValueError:
        return None


def _format_tick(ms: float) -> str:
    try:
        return datetime.fromtimestamp(ms / 1000.0).strftime("%m-%d %H:%M")
    except (OverflowError, OSError, ValueError):
        return str(int(ms))


def _nice_max(value: float) -> float:
    if value <= 0:
        return 1.0
    exp = math.floor(math.log10(value))
    base = 10**exp
    scaled = value / base
    if scaled <= 1:
        nice = 1
    elif scaled <= 2:
        nice = 2
    elif scaled <= 5:
        nice = 5
    else:
        nice = 10
    return nice * base


def render_whatap_json_svg(model: dict[str, Any]) -> str:
    width, height = 860, 360
    pad_l, pad_r, pad_t, pad_b = 56, 24, 48, 72
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b

    series_list = model.get("series") or []
    all_points: list[tuple[float, float]] = []
    normalized_series: list[tuple[str, list[tuple[float, float]]]] = []
    for index, item in enumerate(series_list):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or f"series-{index + 1}")
        points: list[tuple[float, float]] = []
        for raw in item.get("points") or []:
            parsed = _parse_point(raw)
            if parsed is None:
                continue
            t_ms = _parse_time_ms(parsed[0])
            if t_ms is None:
                continue
            points.append((t_ms, parsed[1]))
            all_points.append((t_ms, parsed[1]))
        if points:
            normalized_series.append((name, points))

    if all_points:
        min_t = min(t for t, _ in all_points)
        max_t = max(t for t, _ in all_points)
        max_v = _nice_max(max((v for _, v in all_points), default=1.0))
    else:
        min_t = _parse_time_ms(str(model.get("from") or "")) or 0.0
        max_t = _parse_time_ms(str(model.get("to") or "")) or (min_t + 1.0)
        max_v = 1.0
    span_t = max(1.0, max_t - min_t)

    metric = str(model.get("metric") or "metric")
    unit = str(model.get("unit") or "").strip()
    project = str(model.get("project") or "").strip()
    source = str(model.get("source") or "").strip()
    title = " ".join(
        part
        for part in (
            metric,
            f"({unit})" if unit else "",
            f"· project {project}" if project else "",
        )
        if part
    )

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img">',
        f'<rect width="100%" height="100%" fill="{_THEME["background"]}" rx="8" />',
        f'<text x="{pad_l}" y="24" fill="{_THEME["title"]}" font-size="15" font-weight="600" '
        f'font-family="ui-sans-serif,system-ui,sans-serif">{escape(title)}</text>',
    ]
    if source:
        parts.append(
            f'<text x="{pad_l}" y="42" fill="{_THEME["subtitle"]}" font-size="11" '
            f'font-family="ui-sans-serif,system-ui,sans-serif">{escape(source)}</text>'
        )
    parts.append(
        f'<rect x="{pad_l}" y="{pad_t}" width="{plot_w}" height="{plot_h}" '
        f'fill="{_THEME["plot_fill"]}" stroke="{_THEME["plot_stroke"]}" />'
    )

    y_ticks = 4
    for i in range(y_ticks + 1):
        ratio = i / y_ticks
        y = pad_t + plot_h * (1 - ratio)
        value = max_v * ratio
        label = f"{value:.0f}" if value >= 10 else f"{value:.1f}"
        parts.append(
            f'<line x1="{pad_l}" y1="{y:.1f}" x2="{pad_l + plot_w:.1f}" y2="{y:.1f}" '
            f'stroke="{_THEME["grid"]}" stroke-width="1" />'
        )
        parts.append(
            f'<text x="{pad_l - 8}" y="{y + 4:.1f}" text-anchor="end" fill="{_THEME["axis_label"]}" '
            f'font-size="11" font-family="ui-sans-serif,system-ui,sans-serif">{escape(label)}</text>'
        )

    x_ticks = 4
    for i in range(x_ticks + 1):
        ratio = i / x_ticks
        x = pad_l + plot_w * ratio
        t = min_t + span_t * ratio
        parts.append(
            f'<text x="{x:.1f}" y="{height - 36}" text-anchor="middle" fill="{_THEME["axis_label"]}" '
            f'font-size="11" font-family="ui-sans-serif,system-ui,sans-serif">'
            f"{escape(_format_tick(t))}</text>"
        )

    for index, (name, points) in enumerate(normalized_series):
        color = _SERIES_COLORS[index % len(_SERIES_COLORS)]
        coords: list[str] = []
        for t, v in points:
            x = pad_l + ((t - min_t) / span_t) * plot_w
            y = pad_t + (1 - (v / max_v)) * plot_h
            coords.append(f"{x:.1f},{y:.1f}")
        if len(coords) >= 2:
            parts.append(
                f'<polyline fill="none" stroke="{color}" stroke-width="2.2" '
                f'stroke-linejoin="round" stroke-linecap="round" points="{" ".join(coords)}" />'
            )
        elif len(coords) == 1:
            x, y = coords[0].split(",")
            parts.append(f'<circle cx="{x}" cy="{y}" r="3.5" fill="{color}" />')
        lx = pad_l + (index % 3) * 260
        ly = height - 14
        parts.append(f'<rect x="{lx}" y="{ly - 9}" width="10" height="10" rx="2" fill="{color}" />')
        parts.append(
            f'<text x="{lx + 16}" y="{ly}" fill="{_THEME["legend"]}" font-size="11" '
            f'font-family="ui-sans-serif,system-ui,sans-serif">{escape(name)}</text>'
        )

    parts.append("</svg>")
    return "".join(parts)


def _svg_to_png(svg_bytes: bytes) -> bytes | None:
    rsvg = shutil.which("rsvg-convert")
    if rsvg is None:
        return None
    try:
        completed = subprocess.run(
            [rsvg, "-f", "png"],
            input=svg_bytes,
            check=True,
            capture_output=True,
            timeout=60,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        stderr = getattr(exc, "stderr", b"") or str(exc).encode()
        logger.warning("Whatap chart SVG to PNG failed: %s", stderr.decode(errors="replace"))
        return None
    return completed.stdout or None


def render_whatap_json_image(model: dict[str, Any]) -> tuple[bytes, str] | None:
    try:
        svg_text = render_whatap_json_svg(model)
    except Exception:
        logger.exception("Whatap chart SVG render failed")
        return None
    svg_bytes = svg_text.encode("utf-8")
    png_bytes = _svg_to_png(svg_bytes)
    if png_bytes:
        return png_bytes, "png"
    return svg_bytes, "svg+xml"


def _image_html(data: bytes, mime_subtype: str) -> str:
    encoded = base64.standard_b64encode(data).decode("ascii")
    return (
        f'<img src="data:image/{mime_subtype};base64,{encoded}" '
        'alt="Whatap performance chart" '
        'style="max-width:100%;height:auto;display:block;margin:12px 0;" />'
    )


def apply_whatap_json_to_email_markdown(markdown_text: str) -> tuple[str, str]:
    """Replace whatap-json fences with chart images in HTML markdown."""
    plain_body = markdown_text
    html_markdown = markdown_text

    for match in reversed(list(WHATAP_FENCE_PATTERN.finditer(markdown_text))):
        model = parse_whatap_json(match.group(1))
        if model is None:
            continue
        rendered = render_whatap_json_image(model)
        if rendered is None:
            continue
        image_bytes, mime_subtype = rendered
        start, end = match.span()
        plain_body = plain_body[:start] + f"\n{_PLAIN_CHART_PLACEHOLDER}\n" + plain_body[end:]
        html_markdown = (
            html_markdown[:start]
            + f"\n{_image_html(image_bytes, mime_subtype)}\n"
            + html_markdown[end:]
        )

    return plain_body, html_markdown
