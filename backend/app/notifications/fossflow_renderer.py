"""Render FossFLOW compact JSON as images for HTML email bodies."""

from __future__ import annotations

import base64
import html
import json
import logging
import math
import re
import shutil
import subprocess
from typing import Any

logger = logging.getLogger(__name__)

FENCE_PATTERN = re.compile(r"```([^\n`]*)\r?\n(.*?)```", re.DOTALL)
_PLAIN_DIAGRAM_PLACEHOLDER = "[FossFLOW 다이어그램]"

UNPROJECTED_TILE_SIZE = 100
PROJECTED_TILE = (UNPROJECTED_TILE_SIZE * 1.415, UNPROJECTED_TILE_SIZE * 0.819)
ISO_MATRIX = (0.707, -0.409, 0.707, 0.409, 0, -0.816)
ICON_WIDTH = PROJECTED_TILE[0] * 0.8
ICON_HEIGHT = ICON_WIDTH * 0.623
CONNECTOR_SEARCH_OFFSET = (1, 1)
CONNECTOR_WIDTH = 10
CONNECTOR_STROKE = "#5c88df"
DIAGRAM_BG = "#f6faff"
LABEL_HEIGHT = 80
LABEL_MAX_WIDTH = 250
GRID_PADDING_TILES = 3
PADDING = 48
FONT_FAMILY = "Roboto, Arial, sans-serif"


def is_fossflow_compact(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    meta = value.get("_")
    if not isinstance(meta, dict) or meta.get("f") != "compact":
        return False
    return isinstance(value.get("i"), list) and isinstance(value.get("v"), list)


def parse_fossflow_compact(text: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parsed if is_fossflow_compact(parsed) else None


def _escape(value: str) -> str:
    return html.escape(value, quote=True)


def _wrap_text(text: str, max_chars: int, max_lines: int) -> list[str]:
    trimmed = text.strip()
    if not trimmed:
        return []
    words = trimmed.split()
    lines: list[str] = []
    current = ""
    for word in words:
        next_line = f"{current} {word}".strip()
        if len(next_line) <= max_chars:
            current = next_line
            continue
        if current:
            lines.append(current)
        current = f"{word[: max_chars - 1]}…" if len(word) > max_chars else word
    if current:
        lines.append(current)
    if len(lines) <= max_lines:
        return lines
    kept = lines[:max_lines]
    last = kept[-1]
    kept[-1] = last if last.endswith("…") else f"{last[: max(1, len(last) - 1)]}…"
    return kept


def _tile_to_screen(tile: dict[str, float], origin: str) -> tuple[float, float]:
    half_w = PROJECTED_TILE[0] / 2
    half_h = PROJECTED_TILE[1] / 2
    x = half_w * tile["x"] - half_w * tile["y"]
    y = -(half_h * tile["x"] + half_h * tile["y"])
    if origin == "TOP":
        return x, y - half_h
    if origin == "BOTTOM":
        return x, y + half_h
    if origin == "LEFT":
        return x - half_w, y
    if origin == "RIGHT":
        return x + half_w, y
    return x, y


def _sort_tiles(tiles: list[dict[str, float]]) -> tuple[float, float, float, float]:
    xs = [tile["x"] for tile in tiles]
    ys = [tile["y"] for tile in tiles]
    return min(xs), max(xs), min(ys), max(ys)


def _greedy_path(start: dict[str, int], end: dict[str, int]) -> list[dict[str, int]]:
    path = [{"x": start["x"], "y": start["y"]}]
    x, y = start["x"], start["y"]
    while x != end["x"] or y != end["y"]:
        if x != end["x"]:
            x += 1 if end["x"] > x else -1
        if y != end["y"]:
            y += 1 if end["y"] > y else -1
        path.append({"x": x, "y": y})
    return path


def _connector_path(from_tile: dict[str, float], to_tile: dict[str, float]) -> tuple[list[dict[str, int]], dict[str, dict[str, int]]]:
    anchors = [
        {"x": int(from_tile["x"]), "y": int(from_tile["y"])},
        {"x": int(to_tile["x"]), "y": int(to_tile["y"])},
    ]
    low_x, high_x, low_y, high_y = _sort_tiles(anchors)
    search_low_x = int(low_x - CONNECTOR_SEARCH_OFFSET[0])
    search_high_x = int(high_x + CONNECTOR_SEARCH_OFFSET[0])
    search_low_y = int(low_y - CONNECTOR_SEARCH_OFFSET[1])
    search_high_y = int(high_y + CONNECTOR_SEARCH_OFFSET[1])
    rectangle = {
        "from": {"x": search_high_x, "y": search_high_y},
        "to": {"x": search_low_x, "y": search_low_y},
    }
    normalised = [
        {"x": rectangle["from"]["x"] - pos["x"], "y": rectangle["from"]["y"] - pos["y"]}
        for pos in anchors
    ]
    return _greedy_path(normalised[0], normalised[1]), rectangle


def _iso_projection(from_tile: dict[str, int], to_tile: dict[str, int]) -> tuple[tuple[float, float], tuple[float, float]]:
    px_size = (
        (abs(from_tile["x"] - to_tile["x"]) + 1) * UNPROJECTED_TILE_SIZE,
        (abs(from_tile["y"] - to_tile["y"]) + 1) * UNPROJECTED_TILE_SIZE,
    )
    low_x, high_x, low_y, high_y = _sort_tiles([from_tile, to_tile])
    origin = {"x": low_x, "y": high_y}
    return _tile_to_screen(origin, "LEFT"), px_size


def _apply_iso(point: tuple[float, float]) -> tuple[float, float]:
    a, b, c, d, e, f = ISO_MATRIX
    x, y = point
    return a * x + c * y + e, b * x + d * y + f


def _direction_icon(tiles: list[dict[str, int]]) -> tuple[float, float, int] | None:
    if len(tiles) < 2:
        return None
    icon_tile = tiles[-2]
    last_tile = tiles[-1]
    rotation = -90
    if last_tile["x"] > icon_tile["x"]:
        if last_tile["y"] > icon_tile["y"]:
            rotation = 135
        elif last_tile["y"] < icon_tile["y"]:
            rotation = 45
        else:
            rotation = 90
    elif last_tile["x"] < icon_tile["x"]:
        if last_tile["y"] > icon_tile["y"]:
            rotation = -135
        elif last_tile["y"] < icon_tile["y"]:
            rotation = -45
        else:
            rotation = -90
    elif last_tile["y"] > icon_tile["y"]:
        rotation = 180
    elif last_tile["y"] < icon_tile["y"]:
        rotation = 0
    return (
        icon_tile["x"] * UNPROJECTED_TILE_SIZE + UNPROJECTED_TILE_SIZE / 2,
        icon_tile["y"] * UNPROJECTED_TILE_SIZE + UNPROJECTED_TILE_SIZE / 2,
        rotation,
    )


def compact_to_scene(model: dict[str, Any]) -> dict[str, Any]:
    items = model.get("i") or []
    views = model.get("v") or []
    first = views[0] if views else [[], []]
    positions = first[0] if isinstance(first, list) and first else []
    connections = first[1] if isinstance(first, list) and len(first) > 1 else []
    tile_by_index: dict[int, dict[str, float]] = {}
    for pos in positions:
        if not isinstance(pos, list) or not pos or not isinstance(pos[0], (int, float)):
            continue
        index = int(pos[0])
        tile_by_index[index] = {
            "x": float(pos[1]) if len(pos) > 1 else 0,
            "y": float(pos[2]) if len(pos) > 2 else 0,
        }
    nodes = []
    for index, item in enumerate(items):
        if not isinstance(item, list):
            continue
        nodes.append(
            {
                "index": index,
                "name": str(item[0] if item else ""),
                "description": str(item[2] if len(item) > 2 else ""),
                "tile": tile_by_index.get(index, {"x": 0.0, "y": 0.0}),
            }
        )
    connectors = []
    for conn in connections:
        if not isinstance(conn, list) or len(conn) < 2:
            continue
        if not isinstance(conn[0], (int, float)) or not isinstance(conn[1], (int, float)):
            continue
        connectors.append({"fromIndex": int(conn[0]), "toIndex": int(conn[1])})
    return {
        "title": str(model.get("t") or "Untitled"),
        "nodes": nodes,
        "connectors": connectors,
    }


def render_fossflow_svg(model: dict[str, Any]) -> str:
    scene = compact_to_scene(model)
    nodes = scene["nodes"]
    if not nodes:
        return (
            '<svg xmlns="http://www.w3.org/2000/svg" width="320" height="120" viewBox="0 0 320 120">'
            f'<rect width="100%" height="100%" fill="{DIAGRAM_BG}"/>'
            f'<text x="160" y="64" text-anchor="middle" fill="#64748b" font-size="14" font-family="{FONT_FAMILY}">빈 다이어그램</text>'
            "</svg>"
        )

    node_by_index = {node["index"]: node for node in nodes}
    layouts = []
    bound_points: list[tuple[float, float]] = []
    for node in nodes:
        bottom = _tile_to_screen(node["tile"], "BOTTOM")
        center = _tile_to_screen(node["tile"], "CENTER")
        name_lines = _wrap_text(node["name"], 28, 2)
        desc_lines = _wrap_text(node["description"], 32, 3)
        name_width = max((len(line) * 8.2 for line in name_lines), default=0)
        desc_width = max((len(line) * 7 for line in desc_lines), default=0)
        card_w = min(LABEL_MAX_WIDTH, max(96, name_width, desc_width) + 24)
        card_h = 16 + len(name_lines) * 18 + len(desc_lines) * 16 + (6 if name_lines and desc_lines else 0)
        icon_x = bottom[0] - ICON_WIDTH / 2
        icon_y = bottom[1] - ICON_HEIGHT
        card_x = center[0] - card_w / 2
        card_y = center[1] - LABEL_HEIGHT - card_h
        layout = {
            "node": node,
            "bottom": bottom,
            "center": center,
            "icon_x": icon_x,
            "icon_y": icon_y,
            "name_lines": name_lines,
            "desc_lines": desc_lines,
            "card_w": card_w,
            "card_h": card_h,
            "card_x": card_x,
            "card_y": card_y,
        }
        layouts.append(layout)
        bound_points.extend(
            [
                (icon_x, icon_y),
                (icon_x + ICON_WIDTH, bottom[1]),
                (card_x, card_y),
                (card_x + card_w, card_y + card_h),
            ]
        )

    def connector_markup(from_node: dict[str, Any], to_node: dict[str, Any], ox: float, oy: float) -> tuple[str, list[tuple[float, float]]]:
        tiles, rectangle = _connector_path(from_node["tile"], to_node["tile"])
        if not tiles:
            return "", []
        position, px_size = _iso_projection(rectangle["from"], rectangle["to"])
        draw_offset = UNPROJECTED_TILE_SIZE / 2
        unprojected = [
            (tile["x"] * UNPROJECTED_TILE_SIZE + draw_offset, tile["y"] * UNPROJECTED_TILE_SIZE + draw_offset)
            for tile in tiles
        ]
        points_attr = " ".join(f"{x},{y}" for x, y in unprojected)
        projected = []
        for x, y in unprojected:
            mirrored = (px_size[0] - x, y)
            iso = _apply_iso(mirrored)
            projected.append((iso[0] + position[0], iso[1] + position[1]))
        direction = _direction_icon(tiles)
        arrow = ""
        if direction:
            arrow = (
                f'<g transform="translate({direction[0]}, {direction[1]}) rotate({direction[2]})">'
                '<polygon fill="#000000" stroke="#ffffff" stroke-width="4" points="17.58,17.01 0,-17.01 -17.58,17.01" />'
                "</g>"
            )
        markup = (
            f'<g transform="translate({position[0] + ox}, {position[1] + oy})">'
            f'<g transform="matrix({ISO_MATRIX[0]} {ISO_MATRIX[1]} {ISO_MATRIX[2]} {ISO_MATRIX[3]} {ISO_MATRIX[4]} {ISO_MATRIX[5]})">'
            f'<g transform="translate({px_size[0] / 2}, {px_size[1] / 2}) scale(-1 1) translate({-px_size[0] / 2}, {-px_size[1] / 2})">'
            f'<polyline points="{points_attr}" fill="none" stroke="#ffffff" stroke-width="{CONNECTOR_WIDTH * 1.4}" '
            'stroke-linecap="round" stroke-linejoin="round" stroke-opacity="0.7" />'
            f'<polyline points="{points_attr}" fill="none" stroke="{CONNECTOR_STROKE}" stroke-width="{CONNECTOR_WIDTH}" '
            'stroke-linecap="round" stroke-linejoin="round" />'
            f"{arrow}</g></g></g>"
        )
        return markup, projected

    for connector in scene["connectors"]:
        from_node = node_by_index.get(connector["fromIndex"])
        to_node = node_by_index.get(connector["toIndex"])
        if not from_node or not to_node:
            continue
        _, points = connector_markup(from_node, to_node, 0, 0)
        bound_points.extend(points)

    tiles = [node["tile"] for node in nodes]
    low_x, high_x, low_y, high_y = _sort_tiles(tiles)
    for x in range(int(low_x) - GRID_PADDING_TILES, int(high_x) + GRID_PADDING_TILES + 1):
        for y in range(int(low_y) - GRID_PADDING_TILES, int(high_y) + GRID_PADDING_TILES + 1):
            bound_points.append(_tile_to_screen({"x": x, "y": y}, "TOP"))
            bound_points.append(_tile_to_screen({"x": x, "y": y}, "BOTTOM"))

    min_x = min(point[0] for point in bound_points)
    min_y = min(point[1] for point in bound_points)
    max_x = max(point[0] for point in bound_points)
    max_y = max(point[1] for point in bound_points)
    width = math.ceil(max_x - min_x + PADDING * 2)
    height = math.ceil(max_y - min_y + PADDING * 2)
    ox = -min_x + PADDING
    oy = -min_y + PADDING

    diamonds = []
    for x in range(int(low_x) - GRID_PADDING_TILES, int(high_x) + GRID_PADDING_TILES + 1):
        for y in range(int(low_y) - GRID_PADDING_TILES, int(high_y) + GRID_PADDING_TILES + 1):
            top = _tile_to_screen({"x": x, "y": y}, "TOP")
            right = _tile_to_screen({"x": x, "y": y}, "RIGHT")
            bottom = _tile_to_screen({"x": x, "y": y}, "BOTTOM")
            left = _tile_to_screen({"x": x, "y": y}, "LEFT")
            diamonds.append(
                f'<polygon points="{top[0] + ox},{top[1] + oy} {right[0] + ox},{right[1] + oy} '
                f'{bottom[0] + ox},{bottom[1] + oy} {left[0] + ox},{left[1] + oy}" '
                'fill="none" stroke="#000000" stroke-opacity="0.15" stroke-width="1" />'
            )

    connectors_svg = []
    for connector in scene["connectors"]:
        from_node = node_by_index.get(connector["fromIndex"])
        to_node = node_by_index.get(connector["toIndex"])
        if not from_node or not to_node:
            continue
        markup, _ = connector_markup(from_node, to_node, ox, oy)
        connectors_svg.append(markup)

    nodes_svg = []
    for layout in sorted(layouts, key=lambda item: -(item["node"]["tile"]["x"] + item["node"]["tile"]["y"])):
        bottom = layout["bottom"]
        x = bottom[0] + ox
        y = bottom[1] + oy
        image = (
            f'<polygon points="{x},{layout["icon_y"] + oy} {x + ICON_WIDTH / 2},{y - ICON_HEIGHT / 2} '
            f'{x},{y} {x - ICON_WIDTH / 2},{y - ICON_HEIGHT / 2}" fill="#93c5fd" stroke="#64748b" />'
        )
        name_lines = layout["name_lines"]
        desc_lines = layout["desc_lines"]
        if not name_lines and not desc_lines:
            nodes_svg.append(f"<g>{image}</g>")
            continue
        center = layout["center"]
        stem = (
            f'<line x1="{center[0] + ox}" y1="{center[1] + oy}" x2="{center[0] + ox}" '
            f'y2="{center[1] - LABEL_HEIGHT + oy}" stroke="#000000" stroke-width="3" '
            'stroke-linecap="round" stroke-dasharray="0 6" />'
        )
        card = (
            f'<rect x="{layout["card_x"] + ox}" y="{layout["card_y"] + oy}" width="{layout["card_w"]}" '
            f'height="{layout["card_h"]}" rx="8" fill="#ffffff" stroke="#bdbdbd" />'
        )
        text_y = layout["card_y"] + oy + 20
        texts = []
        for line in name_lines:
            texts.append(
                f'<text x="{center[0] + ox}" y="{text_y}" text-anchor="middle" fill="#1e293b" '
                f'font-size="14" font-family="{FONT_FAMILY}" font-weight="600">{_escape(line)}</text>'
            )
            text_y += 18
        if name_lines and desc_lines:
            text_y += 4
        for line in desc_lines:
            texts.append(
                f'<text x="{center[0] + ox}" y="{text_y}" text-anchor="middle" fill="#64748b" '
                f'font-size="12" font-family="{FONT_FAMILY}">{_escape(line)}</text>'
            )
            text_y += 16
        nodes_svg.append(f"<g>{stem}{card}{''.join(texts)}{image}</g>")

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
        f'<rect width="100%" height="100%" fill="{DIAGRAM_BG}"/>'
        f'<g pointer-events="none">{"".join(diamonds)}</g>'
        f'{"".join(connectors_svg)}'
        f'{"".join(nodes_svg)}'
        "</svg>"
    )


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
        logger.warning("FossFLOW SVG to PNG conversion failed: %s", stderr.decode(errors="replace"))
        return None
    return completed.stdout or None


def render_fossflow_diagram_image(model: dict[str, Any]) -> tuple[bytes, str] | None:
    try:
        svg_text = render_fossflow_svg(model)
    except Exception:
        logger.exception("FossFLOW SVG render failed")
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
        'alt="FossFLOW diagram" style="max-width:100%;height:auto;display:block;margin:12px 0;" />'
    )


def _iter_compact_objects(text: str) -> list[tuple[int, int, dict[str, Any]]]:
    decoder = json.JSONDecoder()
    found: list[tuple[int, int, dict[str, Any]]] = []
    cursor = 0
    while cursor < len(text):
        start = text.find("{", cursor)
        if start < 0:
            break
        try:
            obj, offset = decoder.raw_decode(text, start)
        except json.JSONDecodeError:
            cursor = start + 1
            continue
        end = start + offset
        if is_fossflow_compact(obj):
            found.append((start, end, obj))
            cursor = end
        else:
            cursor = start + 1
    return found


def apply_fossflow_to_email_markdown(markdown_text: str) -> tuple[str, str]:
    """Replace FossFLOW compact JSON with images in HTML markdown; placeholder in plain text."""
    plain_body = markdown_text
    html_markdown = markdown_text

    for match in reversed(list(FENCE_PATTERN.finditer(markdown_text))):
        compact = parse_fossflow_compact(match.group(2).strip())
        if compact is None:
            continue
        rendered = render_fossflow_diagram_image(compact)
        if rendered is None:
            continue
        image_bytes, mime_subtype = rendered
        start, end = match.span()
        plain_body = plain_body[:start] + f"\n{_PLAIN_DIAGRAM_PLACEHOLDER}\n" + plain_body[end:]
        html_markdown = html_markdown[:start] + f"\n{_image_html(image_bytes, mime_subtype)}\n" + html_markdown[end:]

    remaining = _iter_compact_objects(html_markdown)
    for start, end, compact in reversed(remaining):
        rendered = render_fossflow_diagram_image(compact)
        if rendered is None:
            continue
        image_bytes, mime_subtype = rendered
        # Keep plain in sync: find the same JSON if it still exists.
        json_slice = html_markdown[start:end]
        plain_at = plain_body.find(json_slice)
        if plain_at >= 0:
            plain_body = (
                plain_body[:plain_at] + f"\n{_PLAIN_DIAGRAM_PLACEHOLDER}\n" + plain_body[plain_at + len(json_slice) :]
            )
        html_markdown = html_markdown[:start] + f"\n{_image_html(image_bytes, mime_subtype)}\n" + html_markdown[end:]

    return plain_body.strip(), html_markdown.strip()
