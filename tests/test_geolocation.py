"""Unit test for GPS extraction and Baidu Map reverse geocoding.

Usage:
    python -m pytest tests/test_geolocation.py -v
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.image_utils import extract_gps, extract_datetime
from services.map_service import reverse_geocode, search_nearby_attractions

# Forbidden City, Beijing (WGS84)
TEST_LAT = 39.9163
TEST_LNG = 116.3972


class TestGPSExtraction:
    """Test GPS coordinate extraction from image EXIF."""

    def test_extract_gps_no_exif(self, tmp_path):
        """Test that images without EXIF return None."""
        # tmp_path keeps the file fully closed before it is read; the previous
        # NamedTemporaryFile + unlink inside the with-block fails on Windows.
        from PIL import Image

        path = tmp_path / "no-exif.jpg"
        Image.new("RGB", (10, 10), color="red").save(path, "JPEG")
        assert extract_gps(str(path)) is None, "Image without GPS EXIF should return None"

    def test_extract_gps_nonexistent_file(self, tmp_path):
        """Test that nonexistent file returns None."""
        result = extract_gps(str(tmp_path / "missing.jpg"))
        assert result is None

    def test_extract_datetime_no_exif(self, tmp_path):
        """Test datetime extraction from image without EXIF."""
        from PIL import Image

        path = tmp_path / "no-exif.jpg"
        Image.new("RGB", (10, 10), color="blue").save(path, "JPEG")
        assert extract_datetime(str(path)) is None, "Image without DateTime EXIF should return None"

    def test_extract_datetime_nonexistent_file(self, tmp_path):
        """Test that nonexistent file returns None for datetime."""
        result = extract_datetime(str(tmp_path / "missing.jpg"))
        assert result is None


@pytest.mark.live
class TestBaiduMapReverseGeocode:
    """Test Baidu Map reverse geocoding API."""

    def test_reverse_geocode_forbidden_city(self):
        """Test reverse geocoding of Forbidden City coordinates.

        Requires valid Baidu Map API key.
        """
        address = reverse_geocode(TEST_LAT, TEST_LNG)
        assert address is not None, "Reverse geocode should return an address"
        assert len(address) > 0, "Address should not be empty"
        print(f"\n  Reverse geocode result: {address}")

    def test_reverse_geocode_invalid_coords(self):
        """Test reverse geocoding with invalid coordinates."""
        address = reverse_geocode(999.0, 999.0)
        # Baidu API returns None for invalid coords
        assert address is None, "Invalid coordinates should return None"


@pytest.mark.live
class TestBaiduMapPlaceSearch:
    """Test Baidu Map place search API."""

    def test_search_nearby_attractions_forbidden_city(self):
        """Test searching nearby attractions around Forbidden City.

        Requires valid Baidu Map API key.
        """
        attractions = search_nearby_attractions(TEST_LAT, TEST_LNG, radius=5000)
        assert isinstance(attractions, list), "Should return a list"
        assert len(attractions) > 0, "Should find attractions near Forbidden City"

        print(f"\n  Found {len(attractions)} attractions:")
        for a in attractions:
            print(f"    - {a['name']}: {a['address']}")

        # Verify structure of returned items
        for a in attractions:
            assert "name" in a, "Each attraction should have 'name'"
            assert "address" in a, "Each attraction should have 'address'"

    def test_search_nearby_attractions_invalid_coords(self):
        """Test place search with invalid coordinates."""
        attractions = search_nearby_attractions(999.0, 999.0)
        assert attractions == [], "Invalid coordinates should return empty list"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
