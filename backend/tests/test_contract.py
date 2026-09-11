"""Contract tests (BACKEND_BRIEF.md Step 7).

Two things are asserted here:
1. The backend reproduces every entry in contracts/fixtures.json exactly
   (byte-equality modulo the non-deterministic request_id).
2. The externally visible API contract (API.md) holds — response shape,
   status codes, field names/types, reason codes, provenance — exercised
   against the real FastAPI app, not implementation internals.
"""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app

client = TestClient(app)
FIXTURES_PATH = Path(__file__).resolve().parents[2] / "contracts" / "fixtures.json"
FIXTURES = json.loads(FIXTURES_PATH.read_text())
FIXTURE_REQUEST_ID = "req_FIXTURE"


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _normalize(body):
    if isinstance(body, dict) and "request_id" in body:
        body = dict(body)
        body["request_id"] = FIXTURE_REQUEST_ID
    return body


def _replay(fixture):
    endpoint = fixture["endpoint"]
    if endpoint == "POST /api/v1/recommend":
        return client.post("/api/v1/recommend", json=fixture["request"])
    if endpoint == "POST /api/v1/calculate":
        return client.post("/api/v1/calculate", json=fixture["request"])
    if endpoint == "GET /api/v1/partners":
        return client.get("/api/v1/partners", params=fixture["request"])
    raise AssertionError(f"unknown fixture endpoint {endpoint}")


# --- fixture byte-equality (BACKEND_BRIEF.md Step 7) ------------------------------

SIMPLE_FIXTURE_KEYS = [
    "G1_G2_tailoring", "G4_G5_dairy", "G3_calc", "G6_education",
    "G10_plantation", "G7_blocked_income", "partners_ahmedabad_mfs", "partners_empty",
]


@pytest.mark.parametrize("fixture_key", SIMPLE_FIXTURE_KEYS)
def test_fixture_reproduced_exactly(fixture_key):
    fixture = FIXTURES[fixture_key]
    response = _replay(fixture)
    assert response.status_code == 200
    assert _normalize(response.json()) == fixture["response"]


def test_g8_boundary_fixture_reproduced_exactly_both_sides():
    fixture = FIXTURES["G8_boundary_140k"]
    at_cap = client.post("/api/v1/recommend", json=fixture["at_cap"]["request"])
    over_cap = client.post("/api/v1/recommend", json=fixture["over_cap"]["request"])
    assert _normalize(at_cap.json()) == fixture["at_cap"]["response"]
    assert _normalize(over_cap.json()) == fixture["over_cap"]["response"]


def test_all_documented_fixture_keys_are_present():
    """API.md §6 documents these fixture keys as the mocking contract between
    frontend and backend; the frontend's mock layer serves them verbatim."""
    documented_keys = {
        "G1_G2_tailoring", "G4_G5_dairy", "G3_calc", "G6_education",
        "G10_plantation", "G7_blocked_income", "G8_boundary_140k",
        "partners_ahmedabad_mfs", "partners_empty",
    }
    assert documented_keys <= set(FIXTURES.keys())


# --- /recommend: externally visible contract --------------------------------------

def _business(cost, income=240000, activity_code="TAILORING", **extra):
    profile = {"is_sc": True, "annual_family_income": income, "purpose": "business",
               "activity_code": activity_code, "project_cost": cost}
    profile.update(extra)
    return {"locale": "en", "profile": profile}


def _education(fee, remaining_months=48, **extra):
    education = {"course_code": "BTECH", "study_location": "india", "total_course_fee": fee,
                 "remaining_course_months": remaining_months, "admission_confirmed": True}
    education.update(extra)
    return {"locale": "en", "profile": {"is_sc": True, "annual_family_income": 240000,
                                          "purpose": "education", "education": education}}


def test_recommend_rejects_malformed_request_with_documented_error_envelope():
    r = client.post("/api/v1/recommend", json={"locale": "en", "profile": {}})
    assert r.status_code == 400
    body = r.json()
    assert set(body.keys()) == {"error"}
    assert set(body["error"].keys()) == {"code", "message", "field"}
    assert body["error"]["code"] == "VALIDATION_ERROR"


def test_recommend_120000_yields_four_applicable_options():
    r = client.post("/api/v1/recommend", json=_business(120000))
    body = r.json()
    ids = {o["option_id"] for o in body["options"]}
    assert ids == {"NSFDC_MFS", "NSFDC_AMY", "NSFDC_UNY.COOP", "NSFDC_UNY.SFB"}


def test_recommend_ranking_order_and_recommended_option_id():
    r = client.post("/api/v1/recommend", json=_business(400000, activity_code="DAIRY_FARMING"))
    body = r.json()
    ranks = [o["rank"] for o in body["options"]]
    assert ranks == sorted(ranks)
    assert body["options"][0]["rank"] == 1
    assert body["comparison"]["cheapest_option_id"] == body["options"][0]["option_id"]


def test_recommend_all_eligible_options_present_never_truncated():
    r = client.post("/api/v1/recommend", json=_business(120000))
    body = r.json()
    assert len(body["options"]) == 4


def test_recommend_comparison_object_shape():
    r = client.post("/api/v1/recommend", json=_business(120000))
    comparison = r.json()["comparison"]
    assert set(comparison.keys()) == {
        "cheapest_option_id", "costliest_option_id", "extra_cost_if_worst_route", "message_key",
    }
    assert comparison["message_key"] == "comparison.route_matters"
    assert isinstance(comparison["extra_cost_if_worst_route"], int)


def test_recommend_reason_codes_and_params_shape():
    r = client.post("/api/v1/recommend", json=_business(120000))
    for option in r.json()["options"]:
        for reason in option["reasons"]:
            assert set(reason.keys()) == {"code", "params"}
            assert isinstance(reason["code"], str) and reason["code"].isupper()
            assert isinstance(reason["params"], dict)


def test_recommend_blockers_and_remediation_shape_when_blocked():
    r = client.post("/api/v1/recommend", json=_business(120000, income=650000))
    body = r.json()
    assert body["eligible"] is False
    assert body["options"] == []
    assert body["comparison"] is None
    assert body["documents_required"] == []
    assert body["next_step"] is None
    assert body["blockers"] == [{"code": "INCOME_ABOVE_CEILING", "params": {"provided": 650000, "ceiling": 500000}}]
    assert {r["code"] for r in body["remediation"]} == {"CHECK_NBCFDC", "REAPPLY_IF_INCOME_CHANGES"}


def test_recommend_education_response_shape():
    r = client.post("/api/v1/recommend", json=_education(800000, remaining_months=48))
    body = r.json()
    assert body["eligible"] is True
    els = body["options"][0]
    assert els["scheme_id"] == "NSFDC_ELS"
    assert els["instalment_frequency"] == "quarterly"
    assert els["moratorium_months"] == 60


def test_recommend_documents_required_and_next_step():
    r = client.post("/api/v1/recommend", json=_business(120000))
    body = r.json()
    assert all(set(d.keys()) == {"code", "mandatory"} for d in body["documents_required"])
    assert body["next_step"] == {"key": "next_step.visit_partner", "external_portal": "https://pmsuraj.dosje.gov.in/"}


def test_recommend_provenance_citations_and_caveats_present_on_every_option():
    r = client.post("/api/v1/recommend", json=_business(120000))
    for option in r.json()["options"]:
        assert len(option["citations"]) > 0
        for citation in option["citations"]:
            assert set(citation.keys()) == {"field", "value", "source_url", "as_of"}
            assert citation["source_url"].startswith("https://nsfdc.nic.in")
        assert len(option["caveats"]) > 0
        for caveat in option["caveats"]:
            assert set(caveat.keys()) == {"code", "params"}


def test_recommend_ruleset_version_and_request_id_present():
    r = client.post("/api/v1/recommend", json=_business(120000))
    body = r.json()
    assert body["ruleset_version"] == "2026.09.10"
    assert body["request_id"].startswith("req_")


def test_recommend_money_fields_are_integers():
    r = client.post("/api/v1/recommend", json=_business(120000))
    for option in r.json()["options"]:
        for field in ("project_cost", "sanctionable_amount", "own_contribution_required",
                      "instalment", "monthly_equivalent", "total_outgo", "total_interest",
                      "principal_at_repayment_start"):
            assert isinstance(option[field], int), field


def test_recommend_variant_disabled_by_default():
    r = client.post("/api/v1/recommend", json=_education(800000))
    els = r.json()["options"][0]
    assert els["interest_rate"] == 6.5  # unified_2026, not split_legacy (6.0/7.0)


# --- /calculate: externally visible contract --------------------------------------

@pytest.mark.parametrize("scheme_id,sanctioned,total_months,mor,variant,expected", [
    ("NSFDC_MFS", 108000, 36, 3, None, (10977, 120747, 12747)),
    ("NSFDC_AMY", 108000, 36, 3, None, (12619, 138809, 30809)),
    ("NSFDC_TL", 900000, 84, 6, None, (46518, 1209468, 309468)),
    ("NSFDC_UNY", 360000, 60, 3, "COOP", (26527, 504013, 144013)),
    ("NSFDC_TL", 360000, 84, 6, None, (18607, 483782, 123782)),
    ("NSFDC_ELS", 720000, 144, 60, None, (28777, 1381296, 661296)),
    ("NSFDC_TL", 270000, 84, 12, None, (15417, 370008, 100008)),
], ids=["G1", "G2", "G3", "G4", "G5", "G6", "G10"])
def test_calculate_golden_cases(scheme_id, sanctioned, total_months, mor, variant, expected):
    r = client.post("/api/v1/calculate", json={
        "scheme_id": scheme_id, "channel_variant": variant, "sanctioned_amount": sanctioned,
        "total_period_months": total_months, "moratorium_months": mor, "include_schedule": False,
    })
    body = r.json()
    assert (body["instalment"], body["total_outgo"], body["total_interest"]) == expected


def test_calculate_validation_failure_shape():
    r = client.post("/api/v1/calculate", json={"scheme_id": "NSFDC_MFS", "sanctioned_amount": 125001,
                                                  "total_period_months": 36, "moratorium_months": 3})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"
    assert r.json()["error"]["field"] == "sanctioned_amount"


def test_calculate_unknown_scheme_returns_documented_404():
    r = client.post("/api/v1/calculate", json={"scheme_id": "DOES_NOT_EXIST", "sanctioned_amount": 100000,
                                                  "total_period_months": 36, "moratorium_months": 3})
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "NOT_FOUND"


def test_calculate_cap_behavior_at_and_above():
    at_cap = client.post("/api/v1/calculate", json={"scheme_id": "NSFDC_MFS", "sanctioned_amount": 125000,
                                                       "total_period_months": 36, "moratorium_months": 3})
    above_cap = client.post("/api/v1/calculate", json={"scheme_id": "NSFDC_MFS", "sanctioned_amount": 125001,
                                                          "total_period_months": 36, "moratorium_months": 3})
    assert at_cap.status_code == 200
    assert above_cap.status_code == 400


def test_calculate_moratorium_behavior_plantation_special_cap():
    within = client.post("/api/v1/calculate", json={"scheme_id": "NSFDC_TL", "sanctioned_amount": 270000,
                                                       "total_period_months": 84, "moratorium_months": 12})
    beyond = client.post("/api/v1/calculate", json={"scheme_id": "NSFDC_TL", "sanctioned_amount": 270000,
                                                       "total_period_months": 84, "moratorium_months": 13})
    assert within.status_code == 200
    assert beyond.status_code == 400


def test_calculate_response_field_set_and_types():
    r = client.post("/api/v1/calculate", json={"scheme_id": "NSFDC_TL", "sanctioned_amount": 900000,
                                                  "total_period_months": 84, "moratorium_months": 6,
                                                  "include_schedule": True})
    body = r.json()
    assert set(body.keys()) == {
        "scheme_id", "interest_rate", "instalment_frequency", "sanctioned_amount",
        "moratorium_months", "moratorium_treatment", "principal_at_repayment_start",
        "number_of_instalments", "instalment", "monthly_equivalent", "total_outgo",
        "total_interest", "indicative", "data_tier", "schedule",
    }
    for field in ("sanctioned_amount", "principal_at_repayment_start", "instalment",
                  "monthly_equivalent", "total_outgo", "total_interest", "number_of_instalments"):
        assert isinstance(body[field], int)
    for row in body["schedule"]:
        assert set(row.keys()) == {"n", "due_month", "instalment", "interest", "principal", "balance"}


# --- /partners: externally visible contract ---------------------------------------

def test_partners_is_get_not_post():
    r = client.post("/api/v1/partners", json={})
    assert r.status_code == 405
    r_get = client.get("/api/v1/partners", params={"scheme_id": "NSFDC_MFS", "lat": 23.0225, "lng": 72.5714})
    assert r_get.status_code == 200


def test_partners_query_parameter_contract():
    r = client.get("/api/v1/partners", params={
        "scheme_id": "NSFDC_MFS", "lat": 23.0225, "lng": 72.5714, "radius_km": 25, "limit": 10,
    })
    assert r.status_code == 200
    assert set(r.json()["query"].keys()) == {
        "scheme_id", "lat", "lng", "state_code", "district", "radius_km", "limit",
    }


def test_partners_scheme_filtering_contract():
    r = client.get("/api/v1/partners", params={"scheme_id": "NSFDC_AMY", "lat": 23.0225, "lng": 72.5714, "radius_km": 25})
    body = r.json()
    for p in body["partners"]:
        assert "NSFDC_AMY" in p["schemes_supported"]


def test_partners_location_handling_missing_returns_validation_error():
    r = client.get("/api/v1/partners", params={"scheme_id": "NSFDC_MFS"})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_partners_radius_and_limit_contract():
    r = client.get("/api/v1/partners", params={
        "scheme_id": "NSFDC_MFS", "lat": 23.0225, "lng": 72.5714, "radius_km": 5, "limit": 1,
    })
    body = r.json()
    assert len(body["partners"]) <= 1
    assert body["query"]["radius_km"] == 5


def test_partners_routing_status_contract():
    r = client.get("/api/v1/partners", params={"scheme_id": "NSFDC_AMY", "lat": 23.0225, "lng": 72.5714, "radius_km": 25})
    body = r.json()
    for p in body["partners"]:
        assert p["routing_status"] in ("ACCEPTING", "LIMITED")


def test_partners_excluded_shape_contract():
    r = client.get("/api/v1/partners", params={"scheme_id": "NSFDC_AMY", "lat": 23.0225, "lng": 72.5714, "radius_km": 25})
    excluded = r.json()["excluded"]
    assert set(excluded.keys()) == {"count", "items"}
    assert excluded["count"] == len(excluded["items"])
    for item in excluded["items"]:
        assert item["routing_status"] == "NOT_ACCEPTING"
        assert "distance_km" in item and "schemes_supported" not in item


def test_partners_simulated_data_disclosure_contract():
    r = client.get("/api/v1/partners", params={"scheme_id": "NSFDC_MFS", "lat": 23.0225, "lng": 72.5714})
    body = r.json()
    assert body["data_tier"] == "SIMULATED"
    assert body["disclaimer_key"] == "partners.dataset_simulated"


def test_partners_exact_field_names_on_partner_object():
    r = client.get("/api/v1/partners", params={"scheme_id": "NSFDC_MFS", "lat": 23.0225, "lng": 72.5714, "radius_km": 5})
    partner = r.json()["partners"][0]
    assert set(partner.keys()) == {
        "partner_id", "name", "branch_label", "type", "address", "district", "state",
        "state_code", "pincode", "lat", "lng", "phone", "distance_km", "schemes_supported",
        "routing_status", "routing_reasons", "indicators", "data_tier",
    }
    assert set(partner["indicators"].keys()) == {"fund_utilisation_pct", "overdue_ratio_pct", "avg_sanction_days"}
