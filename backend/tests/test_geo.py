"""Haversine distance tests (BACKEND_BRIEF.md Step 6)."""
import math

from app.engine.geo import haversine_km, round_distance_km


def test_identical_coordinates_are_zero_km():
    assert haversine_km(23.0225, 72.5714, 23.0225, 72.5714) == 0.0


def test_known_coordinate_pair_ahmedabad_to_mumbai():
    # Ahmedabad (23.0225, 72.5714) to Mumbai (19.0760, 72.8777): ~440 km straight-line
    distance = haversine_km(23.0225, 72.5714, 19.0760, 72.8777)
    assert 430 < distance < 450


def test_symmetry():
    a = haversine_km(23.0225, 72.5714, 24.5854, 73.7125)
    b = haversine_km(24.5854, 73.7125, 23.0225, 72.5714)
    assert math.isclose(a, b, rel_tol=1e-12)


def test_deterministic_result():
    first = haversine_km(23.0301, 72.5806, 23.0225, 72.5714)
    second = haversine_km(23.0301, 72.5806, 23.0225, 72.5714)
    assert first == second


def test_round_distance_km_rounds_to_one_decimal():
    assert round_distance_km(1.34) == 1.3
    assert round_distance_km(1.35) == 1.4 or round_distance_km(1.35) == 1.3  # banker's rounding edge, both acceptable
    assert round_distance_km(0.0) == 0.0
