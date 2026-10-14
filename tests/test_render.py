"""Unit test for magazine-style image rendering service.

Usage:
    python -m pytest tests/test_render.py -v
"""

import os
import sys
import pytest
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.image_render_service import (
    render_journal_image,
    render_journal_to_bytes,
    _parse_journal_sections,
    _wrap_text,
    _get_font,
    STYLE_COLORS,
    STYLE_DECOR,
)
from PIL import Image, ImageDraw


SAMPLE_JOURNAL = """故宫·时光里的金碧辉煌

今天终于打卡了心心念念的故宫！一走进太和殿广场，眼前豁然开朗——金色的琉璃瓦在阳光下闪闪发光，红墙黄瓦、雕梁画栋，每一处都让人惊叹。

人真的超级多，但完全不影响拍照的心情。建议早点来，避开人流高峰。广场上风很大，记得带件外套。

#故宫 #北京旅行 #打卡 #历史遗迹
"""


class TestRenderService:
    """Test image rendering service."""

    @pytest.fixture
    def test_photo(self):
        """Create a simple test photo."""
        img = Image.new("RGB", (400, 300), color=(100, 150, 200))
        draw = ImageDraw.Draw(img)
        draw.ellipse([300, 20, 380, 100], fill=(255, 255, 0))
        draw.polygon([(0, 250), (150, 80), (300, 250)], fill=(34, 139, 34))

        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            img.save(f.name, "JPEG")
            tmp_path = f.name
        yield tmp_path
        os.unlink(tmp_path)

    def test_render_journal_image_single_photo(self, test_photo):
        """Test rendering with single photo."""
        result = render_journal_image(
            journal_text=SAMPLE_JOURNAL,
            image_paths=[test_photo],
            style="xiaohongshu",
            address="北京市东城区故宫博物院",
            datetime_str="2025-10-15 10:30:00",
            weather="晴天",
        )

        assert result is not None
        assert isinstance(result, Image.Image)
        assert result.width == 750
        assert result.height > 500

        print(f"\n  Rendered image size: {result.size}")

    def test_render_journal_image_no_photo(self):
        """Test rendering without photos."""
        result = render_journal_image(
            journal_text=SAMPLE_JOURNAL,
            image_paths=[],
            style="muji",
        )

        assert result is not None
        assert isinstance(result, Image.Image)
        assert result.width == 750
        assert result.height > 200

    def test_render_journal_image_to_bytes(self, test_photo):
        """Test rendering to bytes output."""
        result = render_journal_to_bytes(
            journal_text=SAMPLE_JOURNAL,
            image_paths=[test_photo],
            style="film",
        )

        assert result is not None
        assert isinstance(result, bytes)
        assert len(result) > 0
        # Should be a valid PNG
        assert result[:8] == b'\x89PNG\r\n\x1a\n'

        print(f"\n  Rendered bytes size: {len(result)} bytes")

    @pytest.mark.parametrize("style_key", list(STYLE_COLORS.keys()))
    def test_render_all_styles(self, test_photo, style_key):
        """Test rendering with each style."""
        result = render_journal_image(
            journal_text=SAMPLE_JOURNAL,
            image_paths=[test_photo],
            style=style_key,
        )

        assert result is not None
        assert isinstance(result, Image.Image)
        assert result.width == 750
        assert result.height > 300

        print(f"\n  [{style_key}] Rendered size: {result.size}")

    def test_render_multi_photo(self, test_photo):
        """Test rendering with multiple photos."""
        # Create second photo
        img2 = Image.new("RGB", (300, 400), color=(200, 100, 100))
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            img2.save(f.name, "JPEG")
            tmp2 = f.name

        try:
            result = render_journal_image(
                journal_text=SAMPLE_JOURNAL,
                image_paths=[test_photo, tmp2],
                style="japanese",
            )
            assert result is not None
            assert result.width == 750
            print(f"\n  Multi-photo rendered size: {result.size}")
        finally:
            os.unlink(tmp2)


class TestJournalParsing:
    """Test journal text parsing."""

    def test_parse_complete_journal(self):
        """Test parsing a complete journal with title, body, and tags."""
        sections = _parse_journal_sections(SAMPLE_JOURNAL)
        assert "title" in sections
        assert "body" in sections
        assert "tags" in sections
        assert len(sections["title"]) > 0
        assert len(sections["body"]) > 0
        assert len(sections["tags"]) > 0

        print(f"\n  Title: {sections['title']}")
        print(f"  Tags: {sections['tags']}")

    def test_parse_journal_no_tags(self):
        """Test parsing journal without tags."""
        text = "标题\n\n这是一段正文内容，没有标签。"
        sections = _parse_journal_sections(text)
        assert sections["title"] == "标题"
        assert len(sections["body"]) > 0
        assert sections["tags"] == []

    def test_parse_journal_only_title(self):
        """Test parsing journal with only a title."""
        text = "只有标题"
        sections = _parse_journal_sections(text)
        assert sections["title"] == "只有标题"
        assert sections["body"] == ""


class TestStyleDefinitions:
    """Test that style color/decoration definitions are complete."""

    def test_all_styles_have_colors(self):
        """Verify each style in STYLE_COLORS has all required color keys."""
        required_keys = {"bg", "card_bg", "title", "body", "accent", "meta", "tag", "border", "photo_border", "divider", "card_shadow"}
        for key, colors in STYLE_COLORS.items():
            for rk in required_keys:
                assert rk in colors, f"Style {key} missing color key '{rk}'"

    def test_all_styles_have_decor(self):
        """Verify each style in STYLE_DECOR has decor keys."""
        for key, decor in STYLE_DECOR.items():
            assert "title_underline" in decor
            assert "corner_accent" in decor
            assert "dot_divider" in decor


class TestTextWrapping:
    """Test text wrapping utility."""

    def test_wrap_short_text(self):
        """Test that short text stays on one line."""
        font = _get_font(22)
        lines = _wrap_text("短文本", font, 500)
        assert len(lines) == 1
        assert lines[0] == "短文本"

    def test_wrap_long_text(self):
        """Test that long text wraps to multiple lines."""
        font = _get_font(22)
        long_text = "这是一段很长的文本" * 20
        lines = _wrap_text(long_text, font, 300)
        # Should produce multiple lines
        assert len(lines) > 1

    def test_wrap_preserves_blank_lines(self):
        """Test that blank lines between paragraphs are preserved."""
        font = _get_font(22)
        text = "第一段\n\n第二段"
        lines = _wrap_text(text, font, 500)
        assert "" in lines


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
