"""Read optional location and shooting time without keeping files open."""

import datetime
import math
from typing import Optional, Tuple

from PIL import Image
from PIL.ExifTags import Base, GPS, IFD


def _convert_to_degrees(value) -> float:
    """Convert valid EXIF GPS rationals to decimal degrees."""
    degrees, minutes, seconds = (float(part) for part in value)
    if not all(math.isfinite(part) for part in (degrees, minutes, seconds)):
        raise ValueError("Invalid GPS coordinates")
    if degrees < 0 or not 0 <= minutes < 60 or not 0 <= seconds < 60:
        raise ValueError("Invalid GPS coordinates")
    return degrees + minutes / 60.0 + seconds / 3600.0


def _reference(value) -> str:
    return value.decode("ascii") if isinstance(value, bytes) else str(value)


def extract_gps(image_path: str) -> Optional[Tuple[float, float]]:
    """Extract valid WGS84 GPS coordinates, or None when unavailable."""
    try:
        with Image.open(image_path) as image:
            exif = image.getexif()
            gps = exif.get_ifd(IFD.GPSInfo)
            latitude = _convert_to_degrees(gps[GPS.GPSLatitude])
            longitude = _convert_to_degrees(gps[GPS.GPSLongitude])
            lat_ref = _reference(gps[GPS.GPSLatitudeRef])
            lng_ref = _reference(gps[GPS.GPSLongitudeRef])
            if lat_ref not in ("N", "S") or lng_ref not in ("E", "W"):
                return None
            if lat_ref == "S":
                latitude = -latitude
            if lng_ref == "W":
                longitude = -longitude
            if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
                return None
            return latitude, longitude
    except (OSError, ValueError, TypeError, KeyError, ZeroDivisionError, AttributeError):
        return None


def extract_datetime(image_path: str) -> Optional[str]:
    """Prefer DateTimeOriginal in the EXIF IFD, falling back to DateTime."""
    try:
        with Image.open(image_path) as image:
            exif = image.getexif()
            exif_ifd = exif.get_ifd(IFD.Exif)
            values = (
                exif_ifd.get(Base.DateTimeOriginal),
                exif.get(Base.DateTimeOriginal),
                exif.get(Base.DateTime),
            )
            for value in values:
                if not value:
                    continue
                if isinstance(value, bytes):
                    value = value.decode("ascii")
                try:
                    parsed = datetime.datetime.strptime(value, "%Y:%m:%d %H:%M:%S")
                    return parsed.strftime("%Y-%m-%d %H:%M:%S")
                except (ValueError, TypeError):
                    continue
            return None
    except (OSError, ValueError, TypeError, KeyError, ZeroDivisionError, AttributeError):
        return None
