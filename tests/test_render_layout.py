"""Offline regression tests for content completeness, layout and photo handling."""

import io

import pytest
from PIL import Image, ImageChops, ImageDraw

from services.image_render_service import (
    CANVAS_WIDTH,
    STYLE_COLORS,
    _fit_photo,
    _get_font,
    _load_photo,
    parse_journal_sections,
    render_journal_image,
    render_journal_to_bytes,
)


@pytest.fixture
def photos(tmp_path):
    paths = []
    for index, size in enumerate([(1400, 900), (700, 1400), (1600, 500)]):
        path = tmp_path / f"photo-{index}.png"
        Image.new("RGB", size, (70 + 40 * index, 130, 160)).save(path)
        paths.append(str(path))
    return paths


def test_parser_keeps_long_title_markdown_headings_and_paragraphs():
    title = "这是一个超过旧版六十字符限制的旅行标题" * 6
    sections = parse_journal_sections(
        f"\n## {title}\n\n第一段\n第二行\n\n### 旅途细节\n第三段\n\n#旅行 #回忆\n"
    )
    assert sections["title"] == title
    assert sections["body"] == "第一段\n第二行\n\n### 旅途细节\n第三段"
    assert sections["tags"] == ["#旅行", "#回忆"]


def test_parser_does_not_treat_hash_inside_a_sentence_as_tags():
    sections = parse_journal_sections("标题\n这个 #景点 让我想再来一次\n\n下一段\n＃照片")
    assert "这个 #景点 让我想再来一次\n\n下一段" in sections["body"]
    assert sections["tags"] == ["＃照片"]


@pytest.mark.parametrize("style", list(STYLE_COLORS))
@pytest.mark.parametrize("scale", [1, 2])
def test_every_drawn_text_and_photo_stays_inside_image(monkeypatch, photos, style, scale):
    """Detect real cropped glyphs/blocks, not merely successful PNG encoding."""
    drawn = []
    original_text = ImageDraw.ImageDraw.text
    original_paste = Image.Image.paste

    def checked_text(self, xy, text, *args, **kwargs):
        bbox = self.textbbox(xy, text, font=kwargs.get("font"), anchor=kwargs.get("anchor"))
        assert bbox[0] >= 0 and bbox[1] >= 0, (text, bbox)
        assert bbox[2] <= self._image.width and bbox[3] <= self._image.height, (text, bbox, self._image.size)
        drawn.append(text)
        return original_text(self, xy, text, *args, **kwargs)

    def checked_paste(self, image, box=None, mask=None):
        if isinstance(image, Image.Image) and box is not None and len(box) == 2:
            assert box[0] >= 0 and box[1] >= 0
            assert box[0] + image.width <= self.width
            assert box[1] + image.height <= self.height
        return original_paste(self, image, box, mask)

    monkeypatch.setattr(ImageDraw.ImageDraw, "text", checked_text)
    monkeypatch.setattr(Image.Image, "paste", checked_paste)
    title = "一场值得慢慢记下的旅行" * 12
    tags = [f"#标签{number}" for number in range(30)] + ["#非常长的标签" * 30]
    text = title + "\n\n第一段故事。\n\n第二段故事。\n\n" + " ".join(tags)
    result = render_journal_image(text, photos, style,
                                  address="浙江省杭州市西湖区特别长的地址说明" * 14,
                                  date="2026-10-10", weather="晴，午后有阵雨" * 12, scale=scale)
    assert result.width == CANVAS_WIDTH * scale
    assert any("旅行手帐" in item for item in drawn), "Footer must still be rendered after all tags."
    visible = "".join(drawn)
    assert "#标签29" in visible
    assert "第一段故事" in visible and "第二段故事" in visible


def test_more_tags_increase_canvas_height_without_eating_bottom_margin():
    base = "标题\n\n正文\n\n"
    short = render_journal_image(base + "#标签1", [], "japanese")
    long = render_journal_image(base + " ".join(f"#标签{i}" for i in range(40)), [], "japanese")
    assert long.height > short.height + 100
    bottom = long.crop((0, long.height - 35, long.width, long.height))
    background = Image.new("RGB", bottom.size, STYLE_COLORS["japanese"]["bg"])
    assert ImageChops.difference(bottom, background).getbbox() is None


def test_long_address_is_rendered_completely_instead_of_truncated(monkeypatch):
    drawn = []
    original = ImageDraw.ImageDraw.text

    def record(self, xy, text, *args, **kwargs):
        drawn.append(text)
        return original(self, xy, text, *args, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "text", record)
    address = "杭州市西湖区" * 20 + "最后的门牌号一百二十号"
    short = render_journal_image("标题\n正文", [], "ins", address="杭州")
    long = render_journal_image("标题\n正文", [], "ins", address=address)
    assert long.height > short.height
    assert address in "".join(drawn)


def test_date_explicitly_entered_by_user_overrides_photo_timestamp(monkeypatch):
    drawn = []
    original = ImageDraw.ImageDraw.text

    def record(self, xy, text, *args, **kwargs):
        drawn.append(text)
        return original(self, xy, text, *args, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "text", record)
    render_journal_image("标题\n正文", [], "muji", datetime_str="2025-01-01 12:00:00", date="2026-10-10")
    assert "2026-10-10" in "".join(drawn)
    assert "2025-01-01" not in "".join(drawn)


def test_exif_rotated_photo_and_transparency_are_handled(tmp_path):
    rotated = tmp_path / "rotated.jpg"
    photo = Image.new("RGB", (120, 80), (230, 40, 40))
    exif = Image.Exif()
    exif[274] = 6
    photo.save(rotated, exif=exif)
    assert _load_photo(str(rotated)).size == (80, 120)
    transparent = tmp_path / "transparent.png"
    Image.new("RGBA", (80, 120), (0, 0, 0, 0)).save(transparent)
    loaded = _load_photo(str(transparent))
    assert loaded.mode == "RGB" and loaded.getpixel((0, 0)) == (255, 255, 255)


def test_high_resolution_export_draws_at_double_width(photos):
    text = "标题\n\n第一段故事。\n\n第二段故事。\n#旅行"
    normal = Image.open(io.BytesIO(render_journal_to_bytes(text, photos[:1], "muji")))
    high = Image.open(io.BytesIO(render_journal_to_bytes(text, photos[:1], "muji", scale=2)))
    assert normal.width == 750 and high.width == 1500
    assert abs(high.height - 2 * normal.height) < 40
    # Small source photos keep the same visual size at both export resolutions.
    small = Image.new("RGB", (100, 50), "red")
    assert _fit_photo(small, 600, 400).size == (100, 50)
    assert _fit_photo(small, 1200, 800, max_upscale=2).size == (200, 100)


@pytest.mark.parametrize("scale", [0, 3, -1, True, 1.5, "2"])
def test_invalid_export_scale_is_rejected(scale):
    with pytest.raises(ValueError, match="倍率"):
        render_journal_to_bytes("标题", [], "muji", scale=scale)


def test_japanese_interleaves_writing_with_photos_and_film_adds_frame_notes(monkeypatch, photos):
    events = []
    original_text = ImageDraw.ImageDraw.text

    def record(self, xy, text, *args, **kwargs):
        events.append(text)
        return original_text(self, xy, text, *args, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "text", record)
    text = "标题\n\n第一段故事。\n\n第二段故事。"
    render_journal_image(text, photos[:2], "japanese")
    assert events.index("旅途片段 01") < events.index("第一段故事。") < events.index("旅途片段 02")
    events.clear()
    render_journal_image(text, photos[:2], "film", date="2026-10-10")
    assert "FRAME 01  /  2026-10-10" in events
    assert "FRAME 02  /  2026-10-10" in events


def test_real_bold_chinese_font_when_available():
    regular = _get_font(22)
    bold = _get_font(22, bold=True)
    # This catches the prior ignored bold parameter on supported platforms.
    if hasattr(regular, "path") and any(part in str(regular.path) for part in ["STHeiti", "Noto", "msyh"]):
        if regular.path == bold.path:
            pytest.skip("The system has no separate bold Chinese font installed.")
        assert bold.getname() != regular.getname()


@pytest.mark.parametrize("style", list(STYLE_COLORS))
def test_explicit_empty_title_preserves_body_as_body(monkeypatch, style):
    drawn = []
    original = ImageDraw.ImageDraw.text

    def record(self, xy, text, *args, **kwargs):
        font = kwargs.get("font")
        drawn.append((text, getattr(font, "size", None)))
        return original(self, xy, text, *args, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "text", record)
    sections = {"title": "", "body": "正文第一行\n\n正文第二段", "tags": []}
    render_journal_image("正文第一行\n\n正文第二段", [], style, sections=sections)
    assert ("正文第一行", 22) in drawn
    assert ("正文第二段", 22) in drawn
    assert not any(size == 34 for _, size in drawn), "An empty title must not promote body text."
    assert sections == {"title": "", "body": "正文第一行\n\n正文第二段", "tags": []}


def test_explicit_tag_only_journal_has_tags_and_no_guessed_title(monkeypatch):
    drawn = []
    original = ImageDraw.ImageDraw.text

    def record(self, xy, text, *args, **kwargs):
        drawn.append((text, getattr(kwargs.get("font"), "size", None)))
        return original(self, xy, text, *args, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "text", record)
    content = render_journal_to_bytes("#旅行 #杭州", [], "muji", scale=2,
                                      sections={"title": "", "body": "", "tags": ["旅行", "#杭州"]})
    assert ("#旅行", 36) in drawn and ("#杭州", 36) in drawn
    assert not any(size == 68 for _, size in drawn)
    assert Image.open(io.BytesIO(content)).width == 1500


@pytest.mark.parametrize("sections", [[], {"title": 1}, {"body": []}, {"tags": "旅行"}, {"tags": [1]}])
def test_invalid_explicit_sections_are_rejected(sections):
    with pytest.raises(ValueError, match="手帐"):
        render_journal_to_bytes("标题", [], "ins", sections=sections)
