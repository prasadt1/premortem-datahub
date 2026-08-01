#!/usr/bin/env python3
"""Frame Premortem diagrams for Devpost gallery upload.

Each output is 1800×1200 with a dark canvas, product wordmark, the diagram
inset with a border, and a caption panel on the right — so white diagrams do
not dissolve into Devpost's white page.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
MEDIA = ROOT / "docs" / "media"
OUT = MEDIA / "gallery"

W, H = 1800, 1200
PAD = 48
LEFT = 56
GAP = 28
# Content row between left margin and right pad: 85% diagram / 15% caption
CONTENT_W = W - LEFT - PAD
INSET_W = int(CONTENT_W * 0.85) - GAP // 2
CAPTION_W = CONTENT_W - INSET_W - GAP
BRAND = "#0b0b0b"
ACCENT = "#eb6834"
PANEL = "#161614"
INK = "#fcfcfb"
MUTED = "#b0aea6"
DIAG_BG = "#fcfcfb"

# (source stem, short title, caption body)
SLIDES: list[tuple[str, str, str]] = [
    (
        "binding-problem",
        "The differentiator",
        "Two tables both have order_status. A name grep flags the wrong one. Binding clears the false alarm — decoy false positives 0.50 → 0.00.",
    ),
    (
        "customer-journey",
        "Who it is for",
        "A data engineer at merge time. PR → Impact Analysis → ask the agent → per-query forecast → write-back the next person inherits.",
    ),
    (
        "product-workflow",
        "Full product verbs",
        "Beyond the forecast: repair (22/22 patches), CI gate, notify owners, catalog write-back. One binder — and it refuses when unsure.",
    ),
    (
        "verdict-taxonomy",
        "Four verdicts",
        "HARD, SOFT, UNKNOWN (needs a human), CLEARED (false alarm, named) — scored by remediation blast radius, each with a real query.",
    ),
    (
        "eval-results",
        "Frozen eval",
        "40-query freeze: HARD precision 1.00, decoy false alarms 0.00 — vs treating every dependent as breaking (0.40 accuracy).",
    ),
    (
        "architecture",
        "How it is wired",
        "Catalog-agnostic binder core (no LLM) that composes with DataHub via CatalogClient — Kit, GraphQL, or Fake. One binder shared by classify and repair.",
    ),
    (
        "dual-mcp-flow",
        "Composition",
        "Two MCP servers, one session: DataHub supplies context and receives the write; Premortem rehearses, repairs, returns the payload.",
    ),
]


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_w: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    cur = ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if draw.textlength(trial, font=font) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def frame_one(stem: str, title: str, caption: str) -> Path:
    src = MEDIA / f"{stem}.png"
    if not src.exists():
        raise FileNotFoundError(src)

    canvas = Image.new("RGB", (W, H), BRAND)
    draw = ImageDraw.Draw(canvas)

    # Accent bar under brand
    draw.rectangle((0, 0, 8, H), fill=ACCENT)

    brand_font = _font(36, bold=True)
    small_font = _font(16)

    draw.text((LEFT, PAD), "PREMORTEM", font=brand_font, fill=INK)
    draw.text((LEFT, PAD + 44), "how it breaks, before you merge", font=small_font, fill=MUTED)

    # Diagram inset area (85% of content width)
    inset_x = LEFT
    inset_y = PAD + 90
    inset_w = INSET_W
    inset_h = H - inset_y - PAD

    # White panel for diagram
    draw.rounded_rectangle(
        (inset_x, inset_y, inset_x + inset_w, inset_y + inset_h),
        radius=16,
        fill=DIAG_BG,
        outline="#2a2a28",
        width=2,
    )

    diagram = Image.open(src).convert("RGB")
    # Fit diagram inside inset with padding
    inner_pad = 28
    max_w = inset_w - 2 * inner_pad
    max_h = inset_h - 2 * inner_pad
    scale = min(max_w / diagram.width, max_h / diagram.height)
    nw, nh = int(diagram.width * scale), int(diagram.height * scale)
    diagram = diagram.resize((nw, nh), Image.Resampling.LANCZOS)
    dx = inset_x + (inset_w - nw) // 2
    dy = inset_y + (inset_h - nh) // 2
    canvas.paste(diagram, (dx, dy))

    # Caption panel (15% of content width)
    cx = inset_x + inset_w + GAP
    cy = inset_y
    draw.rounded_rectangle(
        (cx, cy, cx + CAPTION_W, cy + inset_h),
        radius=16,
        fill=PANEL,
        outline="#2a2a28",
        width=1,
    )
    tx = cx + 20
    ty = cy + 28
    # Slightly smaller type so 15% panel still reads
    title_font = _font(24, bold=True)
    body_font = _font(18)
    draw.text((tx, ty), title, font=title_font, fill=INK)
    draw.rectangle((tx, ty + 34, tx + 40, ty + 38), fill=ACCENT)

    body_top = ty + 52
    lines = _wrap(draw, caption, body_font, CAPTION_W - 40)
    y = body_top
    for line in lines:
        draw.text((tx, y), line, font=body_font, fill=MUTED)
        y += 26

    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / f"{stem}.png"
    canvas.save(out, "PNG", optimize=True)
    return out


def main() -> None:
    for stem, title, caption in SLIDES:
        path = frame_one(stem, title, caption)
        print(f"wrote {path.relative_to(ROOT)} ({path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
