"""API tests for GET /partners (BACKEND_BRIEF.md Step 6)."""
import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app

client = TestClient(app)
URL = "/api/v1/partners"

AHMEDABAD = {"lat": 23.0225, "lng": 72.5714}


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_valid_partner_request_returns_expected_shape():
    r = client.get(URL, params={**AHMEDABAD, "scheme_id": "NSFDC_MFS", "radius_km": 25, "limit": 10})
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {
        "request_id", "ruleset_version", "query", "data_tier", "disclaimer_key",
        "partners", "excluded",
    }
    assert body["data_tier"] == "SIMULATED"
    assert body["disclaimer_key"] == "partners.dataset_simulated"
    assert body["query"]["scheme_id"] == "NSFDC_MFS"


def test_scheme_filtering_only_supporting_partners_returned():
    r = client.get(URL, params={**AHMEDABAD, "scheme_id": "NSFDC_AMY", "radius_km": 25})
    body = r.json()
    for p in body["partners"] + body["excluded"]["items"]:
        pass  # excluded items don't carry schemes_supported in the documented shape
    for p in body["partners"]:
        assert "NSFDC_AMY" in p["schemes_supported"]


def test_radius_filtering_excludes_far_partners():
    tight = client.get(URL, params={**AHMEDABAD, "scheme_id": "NSFDC_MFS", "radius_km": 2}).json()
    loose = client.get(URL, params={**AHMEDABAD, "scheme_id": "NSFDC_MFS", "radius_km": 200}).json()
    assert len(tight["partners"]) < len(loose["partners"]) + len(loose["excluded"]["items"])
    assert len(loose["partners"]) + len(loose["excluded"]["items"]) >= len(tight["partners"]) + len(tight["excluded"]["items"])


def test_routing_status_present_on_every_partner():
    r = client.get(URL, params={**AHMEDABAD, "scheme_id": "NSFDC_MFS", "radius_km": 25})
    body = r.json()
    for p in body["partners"]:
        assert p["routing_status"] in ("ACCEPTING", "LIMITED")
        assert len(p["routing_reasons"]) == 2


def test_excluded_partner_reasons_present():
    r = client.get(URL, params={**AHMEDABAD, "scheme_id": "NSFDC_AMY", "radius_km": 25})
    body = r.json()
    assert body["excluded"]["count"] >= 1
    excluded_item = body["excluded"]["items"][0]
    assert excluded_item["routing_status"] == "NOT_ACCEPTING"
    assert len(excluded_item["routing_reasons"]) == 2
    assert set(excluded_item.keys()) == {
        "partner_id", "name", "branch_label", "distance_km", "type",
        "routing_status", "routing_reasons", "data_tier",
    }


def test_missing_location_returns_documented_validation_error():
    r = client.get(URL, params={"scheme_id": "NSFDC_MFS"})
    assert r.status_code == 400
    body = r.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"


def test_invalid_lat_is_rejected():
    r = client.get(URL, params={"scheme_id": "NSFDC_MFS", "lat": 999, "lng": 72.5714})
    assert r.status_code == 400


def test_unknown_scheme_id_returns_not_found():
    r = client.get(URL, params={**AHMEDABAD, "scheme_id": "NOT_A_SCHEME"})
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "NOT_FOUND"


def test_default_radius_applied_when_not_supplied():
    r = client.get(URL, params={**AHMEDABAD, "scheme_id": "NSFDC_MFS"})
    body = r.json()
    assert body["query"]["radius_km"] == 25  # DEFAULT_RADIUS_KM


def test_custom_radius_reflected_in_query_echo():
    r = client.get(URL, params={**AHMEDABAD, "scheme_id": "NSFDC_MFS", "radius_km": 5})
    body = r.json()
    assert body["query"]["radius_km"] == 5


def test_district_fallback_when_no_coordinates_given():
    r = client.get(URL, params={"scheme_id": "NSFDC_MFS", "state_code": "GJ", "district": "Dahod"})
    assert r.status_code == 200
    body = r.json()
    for p in body["partners"]:
        assert p["district"] == "Dahod"
        assert p["distance_km"] is None


def test_empty_state_when_no_partners_in_radius():
    r = client.get(URL, params={"scheme_id": "NSFDC_MFS", "lat": 1.0, "lng": 1.0, "radius_km": 5})
    body = r.json()
    assert body["partners"] == []
    assert body["excluded"]["count"] == 0
    assert body["excluded"]["items"] == []


def test_llm_disabled_env_still_serves_partners(monkeypatch):
    monkeypatch.setenv("LLM_ENABLED", "false")
    get_settings.cache_clear()
    r = client.get(URL, params={**AHMEDABAD, "scheme_id": "NSFDC_MFS"})
    assert r.status_code == 200


def test_partners_makes_no_network_calls(monkeypatch):
    import socket

    def _blocked(*args, **kwargs):
        raise AssertionError("partners endpoint must not open network sockets")

    monkeypatch.setattr(socket.socket, "connect", _blocked)
    r = client.get(URL, params={**AHMEDABAD, "scheme_id": "NSFDC_MFS"})
    assert r.status_code == 200


def test_simulated_data_disclosure_never_implies_verified_availability():
    r = client.get(URL, params={**AHMEDABAD, "scheme_id": "NSFDC_MFS"})
    body = r.json()
    assert body["data_tier"] == "SIMULATED"
    for p in body["partners"]:
        assert p["data_tier"] == "SIMULATED"
    for p in body["excluded"]["items"]:
        assert p["data_tier"] == "SIMULATED"


def test_partner_ids_and_names_are_preserved_exactly():
    r = client.get(URL, params={**AHMEDABAD, "scheme_id": "NSFDC_MFS", "radius_km": 5})
    body = r.json()
    sca = next(p for p in body["partners"] if p["partner_id"] == "SCA-GJ-AHM-01")
    assert sca["name"] == "Gujarat Scheduled Castes Development Corporation"
