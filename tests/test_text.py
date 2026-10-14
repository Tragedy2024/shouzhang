"""Unit test for text generation (deepseek-v4-pro) travel journal.

Usage:
    python -m pytest tests/test_text.py -v
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.text_service import generate_journal, regenerate_journal, STYLES, TONES


IMAGE_DESC = """
这是一张在故宫拍摄的照片。照片中是太和殿前广场，
金碧辉煌的宫殿在蓝天白云的映衬下格外壮观。
游客们穿着各式各样的衣服在广场上拍照留念，
阳光洒在金黄色的琉璃瓦上闪闪发光。
"""

ADDRESS = "北京市东城区故宫博物院"
ATTRACTIONS = [
    {"name": "故宫博物院", "address": "北京市东城区景山前街4号"},
    {"name": "天安门广场", "address": "北京市东城区"},
    {"name": "景山公园", "address": "北京市西城区景山前街"},
]
DATETIME = "2025-10-15 10:30:00"


@pytest.mark.live
class TestTextGeneration:
    """Test text model API for travel journal generation."""

    def test_generate_journal_with_all_info(self):
        """Test journal generation with complete input data."""
        result = generate_journal(
            IMAGE_DESC, ADDRESS, ATTRACTIONS, DATETIME,
            location="故宫", mood="震撼", feelings="仿佛穿越回了古代",
            date="2025-10-15", weather="晴天",
        )

        assert result is not None, "Text API should return a result"
        assert isinstance(result, str), "Result should be a string"
        assert len(result) > 0, "Result should not be empty"

        print(f"\n  Generated journal:")
        print(f"  {'-' * 40}")
        print(f"  {result}")
        print(f"  {'-' * 40}")

    def test_generate_journal_without_location(self):
        """Test journal generation without GPS/location data."""
        result = generate_journal(
            image_description="照片中是一碗热气腾腾的兰州拉面，上面撒着翠绿的葱花和香菜。",
            address=None, attractions=[], datetime_str=None,
        )

        assert result is not None
        assert len(result) > 0

        print(f"\n  Generated journal (no location):")
        print(f"  {'-' * 40}")
        print(f"  {result}")
        print(f"  {'-' * 40}")

    def test_generate_journal_empty_description(self):
        """Test that empty image description still returns a result."""
        result = generate_journal(
            image_description="", address=None, attractions=[], datetime_str=None,
        )
        assert result is not None
        assert len(result) > 0


@pytest.mark.live
class TestStyleGeneration:
    """Test journal generation with different styles."""

    @pytest.mark.parametrize("style_key", list(STYLES.keys()))
    def test_generate_with_style(self, style_key):
        """Test journal generation for each supported style."""
        style_name = STYLES[style_key]["name"]
        result = generate_journal(
            IMAGE_DESC, ADDRESS, ATTRACTIONS, DATETIME,
            location="故宫", mood="震撼",
            style=style_key,
        )

        assert result is not None
        assert isinstance(result, str)
        assert len(result) > 0

        print(f"\n  [{style_name}] Generated:")
        print(f"  {'-' * 40}")
        print(f"  {result[:200]}...")
        print(f"  {'-' * 40}")

    def test_unknown_style_falls_back(self):
        """Test that unknown style key falls back to xiaohongshu."""
        result = generate_journal(
            IMAGE_DESC, ADDRESS, ATTRACTIONS, DATETIME,
            style="nonexistent_style",
        )
        assert result is not None
        assert len(result) > 0


@pytest.mark.live
class TestRegeneration:
    """Test journal regeneration with different tones."""

    @pytest.fixture
    def original_journal(self):
        """Generate a base journal for regeneration tests."""
        return generate_journal(
            IMAGE_DESC, ADDRESS, ATTRACTIONS, DATETIME,
            location="故宫", mood="震撼",
        )

    @pytest.mark.parametrize("tone_key", list(TONES.keys()))
    def test_regenerate_with_tone(self, original_journal, tone_key):
        """Test regeneration with each tone."""
        tone_label = TONES[tone_key]["label"]
        result = regenerate_journal(original_journal, tone_key)

        assert result is not None
        assert isinstance(result, str)
        assert len(result) > 0
        assert result != original_journal, "Regenerated text should differ from original"

        print(f"\n  [{tone_label}] Regenerated:")
        print(f"  {'-' * 40}")
        print(f"  {result[:200]}...")
        print(f"  {'-' * 40}")

    def test_regenerate_unknown_tone(self):
        """Test that unknown tone returns original text."""
        original = "测试文本"
        result = regenerate_journal(original, "nonexistent_tone")
        assert result == original

    def test_regenerate_preserves_style(self, original_journal):
        """Test regeneration with explicit style context."""
        result = regenerate_journal(original_journal, "literary", style="ins")
        assert result is not None
        assert len(result) > 0


class TestStyleDefinitions:
    """Test that style and tone definitions are valid."""

    def test_all_styles_have_required_fields(self):
        """Verify each style has name, description, and prompt."""
        for key, config in STYLES.items():
            assert "name" in config, f"Style {key} missing 'name'"
            assert "description" in config, f"Style {key} missing 'description'"
            assert "prompt" in config, f"Style {key} missing 'prompt'"
            assert isinstance(config["prompt"], str)
            assert len(config["prompt"]) > 0

    def test_all_tones_have_required_fields(self):
        """Verify each tone has label and prompt."""
        for key, config in TONES.items():
            assert "label" in config, f"Tone {key} missing 'label'"
            assert "prompt" in config, f"Tone {key} missing 'prompt'"
            assert isinstance(config["prompt"], str)
            assert len(config["prompt"]) > 0

    def test_xiaohongshu_is_default(self):
        """Verify xiaohongshu style exists as the default."""
        assert "xiaohongshu" in STYLES


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
