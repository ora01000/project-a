"""Render D2 diagram fences in markdown for HTML email bodies."""

from __future__ import annotations

import base64
import logging
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from backend.app.notifications.fossflow_renderer import apply_fossflow_to_email_markdown

logger = logging.getLogger(__name__)

D2_FENCE_PATTERN = re.compile(r"```d2\s*\r?\n(.*?)```", re.DOTALL | re.IGNORECASE)

_PLAIN_DIAGRAM_PLACEHOLDER = "[D2 다이어그램]"


def normalize_d2_definition(definition: str) -> str:
    """Match frontend ``d2Normalize.ts`` so LLM output compiles consistently."""
    normalized = definition

    def stroke_dash_replacement(match: re.Match[str]) -> str:
        value = (match.group(1) or "").strip().lower()
        if value in {"", "false", "0"}:
            return "stroke-dash: 0" if value in {"false", "0"} else "stroke-dash: 5"
        if value.isdigit():
            return f"stroke-dash: {value}"
        return "stroke-dash: 5"

    normalized = re.sub(
        r"\.style\.stroke-dashed(?:\s*:\s*([^\n]+))?",
        lambda match: f".style.{stroke_dash_replacement(match)}",
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(
        r"\bstroke-dashed\s*:\s*([^\n]+)",
        stroke_dash_replacement,
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(r"\bstroke-dashed\b", "stroke-dash: 5", normalized, flags=re.IGNORECASE)
    return normalized


def _d2_binary() -> str | None:
    return shutil.which("d2")


def _render_d2_svg(d2_source: str) -> bytes | None:
    binary = _d2_binary()
    if binary is None:
        return None

    with tempfile.TemporaryDirectory(prefix="d2-email-") as tmp_dir:
        tmp_path = Path(tmp_dir)
        input_path = tmp_path / "diagram.d2"
        output_path = tmp_path / "diagram.svg"
        input_path.write_text(normalize_d2_definition(d2_source), encoding="utf-8")

        try:
            subprocess.run(
                [binary, str(input_path), str(output_path), "--pad=24"],
                check=True,
                capture_output=True,
                text=True,
                timeout=60,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            stderr = getattr(exc, "stderr", "") or str(exc)
            logger.warning("D2 compile failed: %s", stderr)
            return None

        if not output_path.exists():
            return None
        return output_path.read_bytes()


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
        logger.warning("SVG to PNG conversion failed: %s", stderr.decode(errors="replace"))
        return None

    return completed.stdout or None


def render_d2_diagram_image(d2_source: str) -> tuple[bytes, str] | None:
    """Return ``(image_bytes, mime_subtype)`` where subtype is ``png`` or ``svg+xml``."""
    svg_bytes = _render_d2_svg(d2_source)
    if svg_bytes is None:
        return None

    png_bytes = _svg_to_png(svg_bytes)
    if png_bytes:
        return png_bytes, "png"
    return svg_bytes, "svg+xml"


def _image_html(data: bytes, mime_subtype: str, *, alt: str = "D2 diagram") -> str:
    encoded = base64.standard_b64encode(data).decode("ascii")
    return (
        f'<img src="data:image/{mime_subtype};base64,{encoded}" '
        f'alt="{alt}" style="max-width:100%;height:auto;display:block;margin:12px 0;" />'
    )


def prepare_markdown_for_email(markdown_text: str) -> tuple[str, str]:
    """Split markdown into plain text and HTML-oriented markdown with embedded diagrams."""
    plain_body, html_markdown = apply_fossflow_to_email_markdown(markdown_text)

    for match in reversed(list(D2_FENCE_PATTERN.finditer(html_markdown))):
        start, end = match.span()
        d2_source = match.group(1).strip()
        rendered = render_d2_diagram_image(d2_source) if d2_source else None

        if rendered is None:
            continue

        image_bytes, mime_subtype = rendered
        html_replacement = f"\n{_image_html(image_bytes, mime_subtype)}\n"
        plain_replacement = f"\n{_PLAIN_DIAGRAM_PLACEHOLDER}\n"

        # D2 fences may already have been removed from plain_body if they overlapped FossFLOW;
        # replace the matching span in the current html_markdown, and the same fence text in plain.
        fence_text = html_markdown[start:end]
        plain_at = plain_body.find(fence_text)
        if plain_at >= 0:
            plain_body = plain_body[:plain_at] + plain_replacement + plain_body[plain_at + len(fence_text) :]
        html_markdown = html_markdown[:start] + html_replacement + html_markdown[end:]

    return plain_body.strip(), html_markdown.strip()
