"""Tests for the /dev backend testing console (BACKEND_BRIEF.md Step 8).

Deliberately not brittle about HTML formatting — only checks that the page
is served, references every endpoint it's meant to exercise, and that
production API behavior is unaffected by its existence.
"""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_dev_returns_200_html():
    r = client.get("/dev")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


def test_dev_page_is_not_empty_and_has_title():
    r = client.get("/dev")
    assert len(r.text) > 500
    assert "Project Sarathi" in r.text
    assert "Backend Dev Console" in r.text


def test_dev_page_references_every_required_endpoint():
    body = client.get("/dev").text
    required_paths = [
        "/api/v1/health",
        "/api/v1/recommend",
        "/api/v1/calculate",
        "/api/v1/partners",
        "/api/v1/schemes",
        "/api/v1/meta/activities",
        "/api/v1/meta/courses",
        "/api/v1/meta/documents",
    ]
    for path in required_paths:
        assert path in body, f"{path} not referenced in /dev"


def test_dev_page_references_g4_expected_values():
    body = client.get("/dev").text
    assert "26527" in body
    assert "504013" in body
    assert "144013" in body


def test_dev_page_has_no_external_script_or_stylesheet_dependencies():
    body = client.get("/dev").text
    assert "cdn." not in body.lower()
    assert "unpkg.com" not in body.lower()
    assert "<script src=\"http" not in body
    assert "googleapis.com" not in body.lower()


def test_dev_is_not_registered_in_openapi_schema():
    schema = client.get("/openapi.json").json()
    assert "/dev" not in schema["paths"]


def test_dev_does_not_change_production_recommend_behavior():
    r = client.post("/api/v1/recommend", json={
        "locale": "en",
        "profile": {"is_sc": True, "annual_family_income": 240000, "purpose": "business",
                     "activity_code": "TAILORING", "project_cost": 120000},
    })
    assert r.status_code == 200
    body = r.json()
    assert body["eligible"] is True
    assert {o["option_id"] for o in body["options"]} == {
        "NSFDC_MFS", "NSFDC_AMY", "NSFDC_UNY.COOP", "NSFDC_UNY.SFB",
    }


def test_dev_does_not_change_production_calculate_behavior():
    r = client.post("/api/v1/calculate", json={
        "scheme_id": "NSFDC_UNY", "channel_variant": "COOP", "sanctioned_amount": 360000,
        "total_period_months": 60, "moratorium_months": 3,
    })
    assert r.status_code == 200
    body = r.json()
    assert (body["instalment"], body["total_outgo"], body["total_interest"]) == (26527, 504013, 144013)


def test_dev_does_not_change_production_partners_behavior():
    r = client.get("/api/v1/partners", params={"scheme_id": "NSFDC_MFS", "lat": 23.0225, "lng": 72.5714})
    assert r.status_code == 200
    assert r.json()["data_tier"] == "SIMULATED"


def test_dev_makes_no_network_calls_to_load(monkeypatch):
    import socket

    def _blocked(*args, **kwargs):
        raise AssertionError("/dev must not open network sockets to render")

    monkeypatch.setattr(socket.socket, "connect", _blocked)
    r = client.get("/dev")
    assert r.status_code == 200
