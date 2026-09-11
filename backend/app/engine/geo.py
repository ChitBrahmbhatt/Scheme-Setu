"""Haversine distance (CLAUDE.md §6, BACKEND_BRIEF.md Step 6).

Pure, no I/O, no geocoding. Coordinates are read from data/partners.json and
the request only; nothing here ever infers or looks up a coordinate from an
address.
"""
import math

EARTH_RADIUS_KM = 6371.0


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in kilometres between two lat/lng points."""
    lat1_r, lng1_r, lat2_r, lng2_r = (math.radians(v) for v in (lat1, lng1, lat2, lng2))
    dlat = lat2_r - lat1_r
    dlng = lng2_r - lng1_r
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlng / 2) ** 2
    c = 2 * math.asin(math.sqrt(a))
    return EARTH_RADIUS_KM * c


def round_distance_km(distance_km: float) -> float:
    """Round to one decimal place, per BACKEND_BRIEF.md Step 6."""
    return round(distance_km, 1)
