"""Magazine-style long image rendering service.

Uses Pillow to compose a visually rich long image featuring:
- Styled photo frames with borders/shadows
- Typographic title and body text
- Card-based layout with per-style color schemes
- Decorative elements (lines, dots, borders)
- Meta info and tag footers
"""

import io
import os
import re
import math
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import List, Optional, Tuple
from PIL import Image, ImageDraw, ImageFont, ImageOps

# Canvas dimensions
CANVAS_WIDTH = 750
PADDING_H = 40
PADDING_V = 40
PHOTO_MAX_HEIGHT = 500
CARD_RADIUS = 16
LINE_SPACING = 1.8

# Optional project font first, then Chinese fonts on common operating systems.
_PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Windows is not always installed on C:, so resolve its font directory from
# WINDIR rather than hard-coding C:/Windows/Fonts. Off Windows this stays a
# relative path that never exists, which keeps the list importable everywhere.
_WINDOWS_FONTS = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"


def _windows_font(name: str) -> str:
    return str(_WINDOWS_FONTS / name)


FONT_PATHS = [
    str(_PROJECT_ROOT / "static/fonts/NotoSansSC-Regular.ttf"),
    str(_PROJECT_ROOT / "static/fonts/NotoSansCJK-Regular.ttc"),
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/System/Library/Fonts/Supplemental/Songti.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansSC-Regular.ttf",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    # Windows regular weights first, heavier weights last resort only.
    _windows_font("msyh.ttc"),
    _windows_font("simhei.ttf"),
    _windows_font("simsun.ttc"),
    _windows_font("Deng.ttf"),
    _windows_font("msyhbd.ttc"),
    _windows_font("msyhl.ttc"),
]

# Color schemes per style
STYLE_COLORS = {
    "ins": {
        "bg": (255, 255, 255),
        "card_bg": (250, 250, 250),
        "title": (30, 30, 30),
        "body": (80, 80, 80),
        "accent": (200, 170, 110),
        "meta": (112, 112, 112),
        "tag": (125, 102, 55),
        "border": (230, 230, 230),
        "photo_border": (240, 240, 240),
        "divider": (220, 220, 220),
        "card_shadow": True,
    },
    "xiaohongshu": {
        "bg": (255, 245, 248),
        "card_bg": (255, 255, 255),
        "title": (200, 50, 80),
        "body": (60, 60, 60),
        "accent": (233, 30, 99),
        "meta": (145, 70, 90),
        "tag": (233, 30, 99),
        "border": (255, 220, 230),
        "photo_border": (255, 235, 240),
        "divider": (255, 210, 220),
        "card_shadow": True,
    },
    "japanese": {
        "bg": (252, 248, 240),
        "card_bg": (255, 255, 250),
        "title": (100, 80, 60),
        "body": (90, 80, 70),
        "accent": (160, 130, 100),
        "meta": (125, 105, 85),
        "tag": (120, 94, 70),
        "border": (235, 225, 210),
        "photo_border": (245, 240, 230),
        "divider": (230, 220, 205),
        "card_shadow": False,
    },
    "film": {
        "bg": (35, 35, 38),
        "card_bg": (45, 45, 48),
        "title": (240, 235, 225),
        "body": (210, 205, 195),
        "accent": (200, 170, 120),
        "meta": (160, 155, 145),
        "tag": (180, 160, 130),
        "border": (60, 60, 65),
        "photo_border": (55, 55, 58),
        "divider": (70, 70, 75),
        "card_shadow": False,
    },
    "muji": {
        "bg": (255, 255, 255),
        "card_bg": (255, 255, 255),
        "title": (50, 50, 50),
        "body": (100, 100, 100),
        "accent": (150, 150, 150),
        "meta": (112, 112, 112),
        "tag": (105, 105, 105),
        "border": (235, 235, 235),
        "photo_border": (245, 245, 245),
        "divider": (230, 230, 230),
        "card_shadow": False,
    },
}

# Card decoration presets per style
STYLE_DECOR = {
    "ins": {"title_underline": True, "corner_accent": True, "dot_divider": False},
    "xiaohongshu": {"title_underline": False, "corner_accent": False, "dot_divider": True},
    "japanese": {"title_underline": True, "corner_accent": False, "dot_divider": False},
    "film": {"title_underline": False, "corner_accent": True, "dot_divider": False},
    "muji": {"title_underline": False, "corner_accent": False, "dot_divider": False},
}


@lru_cache(maxsize=48)
def _get_font(size: int, bold: bool = False, light: bool = False) -> ImageFont.FreeTypeFont:
    """Load a Chinese font, with real weight selection where available.

    JOURNAL_FONT_PATH may point to a deployment's own licensed font. A bundled
    Noto font can also be placed in static/fonts without changing this service.
    """
    configured = os.environ.get("JOURNAL_FONT_PATH", "")
    weighted = [
        str(_PROJECT_ROOT / "static/fonts/NotoSansSC-Bold.ttf"),
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        _windows_font("msyhbd.ttc"),
        _windows_font("simhei.ttf"),
    ] if bold else []
    candidates = ([configured] if configured else []) + weighted + FONT_PATHS
    for path in candidates:
        if not os.path.isfile(path):
            continue
        try:
            # Heiti collections contain traditional at 0 and simplified at 1.
            index = 1 if "STHeiti" in path else 0
            return ImageFont.truetype(path, size, index=index)
        except (OSError, ValueError):
            continue
    # Pillow >= 10.1 ships a scalable last resort. Keep older Pillow working too.
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _text_width(text: str, font: ImageFont.FreeTypeFont) -> int:
    bbox = font.getbbox(text)
    return math.ceil(max(font.getlength(text), bbox[2] - bbox[0]))


def _graphemes(text: str) -> List[str]:
    """Keep combining marks and emoji joiner sequences together while wrapping."""
    units = []
    for char in text:
        if units and (unicodedata.combining(char) or char in "\ufe0e\ufe0f\u200d"
                      or units[-1].endswith("\u200d")
                      or 0x1F3FB <= ord(char) <= 0x1F3FF):
            units[-1] += char
        else:
            units.append(char)
    return units


def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> List[str]:
    """Pixel-based wrapping with paragraph gaps and Latin words preserved."""
    if max_width <= 0:
        raise ValueError("文本区域宽度必须大于 0")
    lines = []
    for paragraph in text.split("\n"):
        if not paragraph.strip():
            lines.append("")
            continue
        line = ""
        # Group Latin words; long words can still break to stay inside the page.
        units = re.findall(r"[A-Za-z0-9]+(?:['’_-][A-Za-z0-9]+)*|[^A-Za-z0-9]", paragraph)
        units = [part for unit in units for part in
                 ([unit] if _text_width(unit, font) <= max_width else _graphemes(unit))]
        # Recombine marks that the token expression treated as separate units.
        combined = []
        for unit in units:
            if combined and (unit in "\ufe0e\ufe0f\u200d" or unicodedata.combining(unit[0])
                             or combined[-1].endswith("\u200d")):
                combined[-1] += unit
            else:
                combined.append(unit)
        for unit in combined:
            if _text_width(line + unit, font) <= max_width:
                line += unit
            else:
                if line:
                    lines.append(line.rstrip())
                line = unit.lstrip()
        if line:
            lines.append(line.rstrip())
    return lines


def parse_journal_sections(journal_text: str) -> dict:
    """Return editable title/body/tags without discarding paragraph breaks.

    The first nonempty line is always the title. Markdown headings use a space
    after their hashes; hashtags do not, so headings stay in the document.
    """
    lines = journal_text.replace("\r\n", "\n").replace("\r", "\n").strip().split("\n")
    if not journal_text.strip():
        return {"title": "", "body": "", "tags": []}
    title = re.sub(r"^#{1,6}\s+", "", lines[0].strip())
    title = re.sub(r"\s+#+$", "", title)
    body_lines, tags = [], []
    for line in lines[1:]:
        stripped = line.strip()
        tokens = stripped.split()
        if tokens and all(re.fullmatch(r"[#＃][^#＃\s]+", token) for token in tokens):
            tags.extend(tokens)
        else:
            body_lines.append(line.rstrip())
    return {"title": title, "body": "\n".join(body_lines).strip(), "tags": tags}


# Preserve imports used by older callers and tests.
_parse_journal_sections = parse_journal_sections


def _line_height(font: ImageFont.FreeTypeFont, extra: int) -> int:
    try:
        ascent, descent = font.getmetrics()
        return ascent + descent + extra
    except AttributeError:
        bbox = font.getbbox("国Ag")
        return bbox[3] - bbox[1] + extra


def _text_block(text: str, width: int, font: ImageFont.FreeTypeFont, colors: dict,
                scale: int, kind: str = "body", card: bool = False,
                style: str = "xiaohongshu") -> Image.Image:
    padding = 22 * scale if card else 0
    lines = _wrap_text(text, font, width - 2 * padding)
    step = _line_height(font, (8 if kind == "title" else 10) * scale)
    gap = step // 2
    heights = [gap if not line else step for line in lines]
    height = max(sum(heights), step) + 2 * padding
    block = Image.new("RGB", (width, height), colors["bg"])
    draw = ImageDraw.Draw(block)
    if card:
        draw.rounded_rectangle((0, 0, width - 1, height - 1), radius=16 * scale,
                               fill=colors["card_bg"], outline=colors["border"], width=scale)
    y = padding
    for line, line_height in zip(lines, heights):
        if line:
            # Render Markdown subheadings as text rather than as hashtag pills.
            visible = re.sub(r"^#{1,6}\s+", "", line)
            draw.text((padding, y), visible, fill=colors[kind], font=font, anchor="lt")
        y += line_height
    if kind == "title" and style in ("ins", "japanese", "film"):
        underline = Image.new("RGB", (width, height + 18 * scale), colors["bg"])
        underline.paste(block, (0, 0))
        ImageDraw.Draw(underline).line((0, height + 10 * scale, 80 * scale, height + 10 * scale),
                                      fill=colors["accent"], width=2 * scale)
        return underline
    return block


def _load_photo(path: str) -> Image.Image:
    """Apply EXIF orientation and flatten transparent photos onto paper white."""
    with Image.open(path) as source:
        photo = ImageOps.exif_transpose(source).convert("RGBA")
        background = Image.new("RGBA", photo.size, "white")
        return Image.alpha_composite(background, photo).convert("RGB")


def _fit_photo(photo: Image.Image, max_width: int, max_height: int,
               max_upscale: int = 1) -> Image.Image:
    """Fit without cropping; high-resolution output preserves the logical size."""
    pw, ph = photo.size
    ratio = min(max_width / pw, max_height / ph, max_upscale)
    size = (max(1, round(pw * ratio)), max(1, round(ph * ratio)))
    return photo.resize(size, Image.Resampling.LANCZOS) if size != photo.size else photo.copy()


def _photo_block(photo: Image.Image, width: int, colors: dict, scale: int,
                 style: str, index: int = 1, stamp: str = "") -> Image.Image:
    frame = 14 * scale if style == "film" else (10 * scale if style == "japanese" else 0)
    fitted = _fit_photo(photo, width - 2 * frame, (440 if style == "muji" else 500) * scale,
                        max_upscale=scale)
    annotation = ""
    if style == "film":
        annotation = f"FRAME {index:02d}" + (f"  /  {stamp}" if stamp else "")
    elif style == "japanese":
        annotation = f"旅途片段 {index:02d}"
    caption_font = _get_font(16 * scale)
    caption_lines = _wrap_text(annotation, caption_font, width - 2 * frame) if annotation else []
    caption_step = _line_height(caption_font, 4 * scale)
    caption_height = len(caption_lines) * caption_step + (20 * scale if caption_lines else 0)
    height = fitted.height + frame * 2 + caption_height
    block = Image.new("RGB", (width, height), colors["bg"])
    draw = ImageDraw.Draw(block)
    if frame:
        draw.rectangle((0, 0, width - 1, height - 1),
                       fill=(250, 248, 242) if style == "film" else colors["photo_border"])
    block.paste(fitted, ((width - fitted.width) // 2, frame))
    # Allow a long user date to wrap, without extending beyond the frame.
    for row, caption in enumerate(caption_lines):
        caption_color = (115, 96, 73) if style == "film" else colors["meta"]
        draw.text((frame, fitted.height + frame + 12 * scale + row * caption_step),
                  caption, fill=caption_color, font=caption_font, anchor="lt")
    return block


def _photo_grid(photos: List[Image.Image], width: int, colors: dict, scale: int) -> Image.Image:
    gap = 12 * scale
    cell_width = (width - gap) // 2
    cell_height = 250 * scale
    rows = (len(photos) + 1) // 2
    block = Image.new("RGB", (width, rows * cell_height + (rows - 1) * gap), colors["bg"])
    draw = ImageDraw.Draw(block)
    for index, photo in enumerate(photos):
        x = (index % 2) * (cell_width + gap)
        y = (index // 2) * (cell_height + gap)
        # Center the last photo in an odd grid instead of leaving a lopsided row.
        if index == len(photos) - 1 and len(photos) % 2:
            x = (width - cell_width) // 2
        draw.rounded_rectangle((x, y, x + cell_width - 1, y + cell_height - 1),
                               radius=12 * scale, fill=colors["photo_border"])
        fitted = _fit_photo(photo, cell_width - 12 * scale, cell_height - 12 * scale,
                            max_upscale=scale)
        block.paste(fitted, (x + (cell_width - fitted.width) // 2,
                             y + (cell_height - fitted.height) // 2))
    return block


def _metadata_block(address: Optional[str], display_time: str, weather: str,
                    width: int, colors: dict, scale: int) -> Optional[Image.Image]:
    items = [(label, value) for label, value in
             [("地点", address), ("日期", display_time), ("天气", weather)] if value]
    if not items:
        return None
    font = _get_font(17 * scale)
    step = _line_height(font, 7 * scale)
    padding = 14 * scale
    measured = [_wrap_text(f"{label}  {value}", font, width - 2 * padding) for label, value in items]
    heights = [len(lines) * step + 2 * padding for lines in measured]
    gap = 8 * scale
    block = Image.new("RGB", (width, sum(heights) + gap * (len(items) - 1)), colors["bg"])
    draw = ImageDraw.Draw(block)
    y = 0
    for lines, height in zip(measured, heights):
        draw.rounded_rectangle((0, y, width - 1, y + height - 1), radius=8 * scale,
                               fill=colors["card_bg"], outline=colors["border"], width=scale)
        for row, line in enumerate(lines):
            draw.text((padding, y + padding + row * step), line, fill=colors["meta"],
                      font=font, anchor="lt")
        y += height + gap
    return block


def _tags_block(tags: List[str], width: int, colors: dict, scale: int) -> Optional[Image.Image]:
    if not tags:
        return None
    font = _get_font(18 * scale)
    step = _line_height(font, 4 * scale)
    padding_x, padding_y, gap = 12 * scale, 8 * scale, 10 * scale
    rows, row, row_width, row_height = [], [], 0, 0
    for tag in tags:
        lines = _wrap_text(tag, font, width - padding_x * 2)
        tag_width = min(width, max(_text_width(line, font) for line in lines) + 2 * padding_x)
        tag_height = len(lines) * step + padding_y * 2
        if row and row_width + gap + tag_width > width:
            rows.append((row, row_height))
            row, row_width, row_height = [], 0, 0
        x = row_width + (gap if row else 0)
        row.append((x, lines, tag_width, tag_height))
        row_width = x + tag_width
        row_height = max(row_height, tag_height)
    if row:
        rows.append((row, row_height))
    height = sum(row_height for _, row_height in rows) + gap * (len(rows) - 1)
    block = Image.new("RGB", (width, height), colors["bg"])
    draw = ImageDraw.Draw(block)
    y = 0
    for row, row_height in rows:
        for x, lines, tag_width, tag_height in row:
            draw.rounded_rectangle((x, y, x + tag_width - 1, y + tag_height - 1),
                                   radius=12 * scale, fill=colors["border"])
            for line_index, line in enumerate(lines):
                draw.text((x + padding_x, y + padding_y + line_index * step), line,
                          fill=colors["tag"], font=font, anchor="lt")
        y += row_height + gap
    return block


def _add_film_grain(image: Image.Image, intensity: float = 0.025) -> Image.Image:
    """Use a small deterministic texture rather than Python per-pixel work."""
    import random
    generator = random.Random(42)
    tile = Image.frombytes("L", (128, 128),
                           bytes(generator.randrange(96, 160) for _ in range(128 * 128)))
    texture = Image.new("L", image.size)
    for y in range(0, image.height, tile.height):
        for x in range(0, image.width, tile.width):
            patch = tile.crop((0, 0, min(tile.width, image.width - x),
                               min(tile.height, image.height - y)))
            texture.paste(patch, (x, y))
    return Image.blend(image, texture.convert("RGB"), intensity)


def _journal_blocks(journal_text: str, photos: List[Image.Image], style: str,
                    address: Optional[str], datetime_str: Optional[str], date: str,
                    weather: str, scale: int,
                    sections: Optional[dict] = None) -> Tuple[List[Tuple[Image.Image, int]], int, int]:
    """Build fully measured blocks; their actual sizes determine canvas height."""
    colors = STYLE_COLORS[style]
    margin = (70 if style == "muji" else 44 if style == "japanese" else PADDING_H) * scale
    width = CANVAS_WIDTH * scale - margin * 2
    gap = (42 if style == "muji" else 28) * scale
    if sections is None:
        sections = parse_journal_sections(journal_text)
    else:
        if not isinstance(sections, dict):
            raise ValueError("手帐结构必须包含标题、正文与标签")
        title, body, tags = sections.get("title", ""), sections.get("body", ""), sections.get("tags", [])
        if not isinstance(title, str) or not isinstance(body, str) or not isinstance(tags, list):
            raise ValueError("手帐标题与正文必须为文字，标签必须为列表")
        if any(not isinstance(tag, str) for tag in tags):
            raise ValueError("每个手帐标签必须为文字")
        # Editor sections are authoritative, including an intentionally empty
        # title or body. Never infer another title from the first body line.
        sections = {"title": title, "body": body,
                    "tags": [tag if tag.startswith(("#", "＃")) else f"#{tag}"
                             for tag in tags if tag.strip()]}
    blocks = []

    def append(block: Optional[Image.Image], space: Optional[int] = None):
        if block is not None:
            blocks.append((block, gap if space is None else space))

    def title():
        if sections["title"]:
            append(_text_block(sections["title"], width, _get_font(34 * scale, bold=True),
                               colors, scale, "title", style in ("ins", "xiaohongshu"), style))

    def body(text: str):
        if text.strip():
            append(_text_block(text, width, _get_font(22 * scale), colors, scale,
                               card=style in ("ins", "xiaohongshu"), style=style))

    # Explicit user date overrides camera time, which can belong to another trip.
    display_time = date or datetime_str or ""
    paragraphs = [part for part in re.split(r"\n\s*\n", sections["body"]) if part.strip()]
    if style in ("japanese", "film"):
        title()
        # Interleave image and writing while preserving the user's paragraph order.
        for index in range(max(len(photos), len(paragraphs))):
            if index < len(photos):
                append(_photo_block(photos[index], width, colors, scale, style,
                                    index + 1, display_time))
            if index < len(paragraphs):
                body(paragraphs[index])
    elif style == "muji":
        title()
        for index, photo in enumerate(photos):
            append(_photo_block(photo, width, colors, scale, style, index + 1))
        body(sections["body"])
    else:
        if len(photos) == 1:
            append(_photo_block(photos[0], width, colors, scale, style))
        elif photos:
            append(_photo_grid(photos, width, colors, scale))
        title()
        body(sections["body"])
    append(_metadata_block(address, display_time, weather, width, colors, scale))
    append(_tags_block(sections["tags"], width, colors, scale))
    names = {"ins": "INS 风", "xiaohongshu": "小红书风", "japanese": "日杂风",
             "film": "胶片风", "muji": "极简风"}
    footer_font = _get_font(15 * scale)
    footer_height = _line_height(footer_font, 12 * scale)
    footer = Image.new("RGB", (width, footer_height), colors["bg"])
    draw = ImageDraw.Draw(footer)
    label = names[style] + " · 旅行手帐"
    draw.text(((width - _text_width(label, footer_font)) // 2, 4 * scale), label,
              font=footer_font, fill=colors["meta"], anchor="lt")
    append(footer, 0)
    return blocks, margin, (60 if style == "muji" else PADDING_V) * scale


def render_journal_image(journal_text: str, image_paths: List[str], style: str,
                         address: Optional[str] = None, datetime_str: Optional[str] = None,
                         date: str = "", weather: str = "", scale: int = 1,
                         sections: Optional[dict] = None) -> Image.Image:
    """Render a complete journal at 750px or 1500px with native-size text.

    Every block is drawn at its measured height before composition, so wrapped
    tags, long metadata and film frames cannot extend outside the canvas.
    Explicit sections preserve editor fields; omitted sections parse plain text.
    """
    if not isinstance(scale, int) or isinstance(scale, bool) or scale not in (1, 2):
        raise ValueError("导出倍率仅支持 1 或 2")
    style = style if style in STYLE_COLORS else "xiaohongshu"
    photos = [_load_photo(path) for path in image_paths]
    blocks, margin, padding = _journal_blocks(journal_text, photos, style, address,
                                              datetime_str, date, weather, scale, sections)
    height = padding * 2 + sum(block.height + gap for block, gap in blocks)
    canvas = Image.new("RGB", (CANVAS_WIDTH * scale, height), STYLE_COLORS[style]["bg"])
    y = padding
    for block, gap in blocks:
        canvas.paste(block, (margin, y))
        y += block.height + gap
    return _add_film_grain(canvas) if style == "film" else canvas


def render_journal_to_bytes(journal_text: str, image_paths: List[str], style: str,
                            address: Optional[str] = None, datetime_str: Optional[str] = None,
                            date: str = "", weather: str = "", scale: int = 1,
                            sections: Optional[dict] = None) -> bytes:
    """Return PNG bytes; scale=2 draws crisp text at twice the default width."""
    image = render_journal_image(journal_text, image_paths, style, address,
                                 datetime_str, date, weather, scale, sections)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()
