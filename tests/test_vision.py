"""Unit test for vision model (qwen2.5-vl-72b) image analysis.

Usage:
    python -m pytest tests/test_vision.py -v
"""

import os
import sys
import pytest
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.vision_service import analyze_image, analyze_images, analyze_images_batch, encode_image
from PIL import Image, ImageDraw


def _create_test_image(color=(100, 150, 200), draw_shapes=True):
    """Helper to create a simple test image."""
    img = Image.new("RGB", (200, 200), color=color)
    if draw_shapes:
        d = ImageDraw.Draw(img)
        d.ellipse([150, 10, 190, 50], fill=(255, 255, 0))
        d.polygon([(0, 150), (80, 50), (160, 150)], fill=(34, 139, 34))
        d.rectangle([(0, 150), (200, 200)], fill=(30, 144, 255))
    return img


class TestVisionModel:
    """Test vision model API for image content analysis."""

    @pytest.fixture
    def test_image(self):
        """Create a test image for vision analysis."""
        img = _create_test_image()
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            img.save(f.name, "JPEG")
            tmp_path = f.name
        yield tmp_path
        os.unlink(tmp_path)

    @pytest.mark.live
    def test_analyze_image_returns_content(self, test_image):
        """Test that vision model returns a description for an image."""
        result = analyze_image(test_image)
        assert result is not None, "Vision API should return a result"
        assert isinstance(result, str), "Result should be a string"
        assert len(result) > 0, "Result should not be empty"

        print(f"\n  Vision analysis result:")
        print(f"    {result[:300]}...")

    def test_analyze_image_nonexistent_file(self):
        """Unreadable photos fail explicitly instead of becoming fiction."""
        from services.errors import GenerationError
        with pytest.raises(GenerationError) as error:
            analyze_image("/nonexistent/image.jpg")
        assert error.value.stage == "vision"
        assert error.value.retryable is False

    def test_encode_image_basic(self, test_image):
        """Test base64 encoding of an image."""
        b64_str = encode_image(test_image)
        assert isinstance(b64_str, str), "Should return a string"
        assert len(b64_str) > 0, "Encoded string should not be empty"
        import base64

        assert len(b64_str) % 4 == 0, "Base64 string length should be multiple of 4"
        decoded = base64.b64decode(b64_str)
        assert len(decoded) > 0, "Decoded bytes should not be empty"


class TestMultiImageAnalysis:
    """Test multi-image analysis."""

    @pytest.fixture
    def two_test_images(self):
        """Create two test images."""
        paths = []
        colors = [(100, 150, 200), (200, 100, 100)]
        for i, color in enumerate(colors):
            img = _create_test_image(color=color)
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
                img.save(f.name, "JPEG")
                paths.append(f.name)
        yield paths
        for p in paths:
            os.unlink(p)

    @pytest.mark.live
    def test_analyze_images_single(self, two_test_images):
        """Test analyze_images with single image delegates correctly."""
        result = analyze_images([two_test_images[0]])
        assert result is not None
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.live
    def test_analyze_images_multiple(self, two_test_images):
        """Test analyze_images with multiple images."""
        result = analyze_images(two_test_images)
        assert result is not None
        assert isinstance(result, str)
        assert len(result) > 0
        # Should contain photo labels
        assert "照片1" in result or "照片2" in result

        print(f"\n  Multi-image analysis result:")
        print(f"    {result[:300]}...")

    @pytest.mark.live
    def test_analyze_images_batch_multiple(self, two_test_images):
        """Test batch analysis of multiple images."""
        result = analyze_images_batch(two_test_images)
        assert result is not None
        assert isinstance(result, str)
        assert len(result) > 0

        print(f"\n  Batch analysis result:")
        print(f"    {result[:300]}...")

    def test_analyze_images_empty_list(self):
        """Test that empty list returns empty string."""
        result = analyze_images([])
        assert result == ""

    def test_analyze_images_batch_empty(self):
        """Test that batch with empty list returns empty string."""
        result = analyze_images_batch([])
        assert result == ""


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
