"""Baidu Map API service for reverse geocoding and place search."""

import requests
import logging
from typing import Optional, Tuple, List, Dict
from config import BAIDU_MAP_CONFIG

logger = logging.getLogger(__name__)


def reverse_geocode(lat: float, lng: float) -> Optional[str]:
    """Convert GPS coordinates to address using Baidu Map reverse geocoding.

    Args:
        lat: Latitude (WGS84).
        lng: Longitude (WGS84).

    Returns:
        Formatted address string, or None on failure.
    """
    try:
        params = {
            "ak": BAIDU_MAP_CONFIG["api_key"],
            "output": "json",
            "coordtype": "wgs84ll",
            "location": f"{lat},{lng}",
        }

        resp = requests.get(
            BAIDU_MAP_CONFIG["reverse_geocode_url"],
            params=params,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("status") == 0:
            return data["result"]["formatted_address"]
        return None
    except Exception as e:
        logger.warning("Reverse geocode failed: %s", type(e).__name__)
        return None


def search_nearby_attractions(
    lat: float, lng: float, radius: int = 5000
) -> List[Dict[str, str]]:
    """Search for nearby tourist attractions using Baidu Map Place API.

    Args:
        lat: Latitude (WGS84).
        lng: Longitude (WGS84).
        radius: Search radius in meters.

    Returns:
        List of attractions, each with 'name' and 'address' keys.
    """
    try:
        params = {
            "ak": BAIDU_MAP_CONFIG["api_key"],
            "output": "json",
            "query": "旅游景点",
            "location": f"{lat},{lng}",
            "radius": radius,
            "scope": 2,  # Detailed scope
            "coord_type": 1,  # WGS84
        }

        resp = requests.get(
            BAIDU_MAP_CONFIG["place_search_url"],
            params=params,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("status") == 0:
            results = []
            for item in data.get("results", [])[:5]:  # Top 5
                results.append({
                    "name": item.get("name", ""),
                    "address": item.get("address", ""),
                })
            return results
        return []
    except Exception as e:
        logger.warning("Place search failed: %s", type(e).__name__)
        return []
