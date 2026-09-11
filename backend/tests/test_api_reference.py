"""API tests for the reference-data endpoints (API.md §4)."""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


# --- GET /schemes -----------------------------------------------------------------

def test_get_schemes_returns_full_raw_structure():
    r = client.get("/api/v1/schemes")
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) >= {
        "ruleset_version", "variants", "eligibility", "assumptions", "schemes",
    }
    assert body["ruleset_version"] == "2026.09.10"
    assert {s["scheme_id"] for s in body["schemes"]} == {
        "NSFDC_MFS", "NSFDC_TL", "NSFDC_AMY", "NSFDC_UNY", "NSFDC_ELS",
    }


def test_get_schemes_exposes_citations_and_data_tier_per_field():
    body = client.get("/api/v1/schemes").json()
    mfs = next(s for s in body["schemes"] if s["scheme_id"] == "NSFDC_MFS")
    assert mfs["data_tier"] == "VERIFIED"
    assert len(mfs["citations"]) > 0
    for c in mfs["citations"]:
        assert set(c.keys()) == {"field", "value", "source_url", "as_of"}


def test_get_schemes_variants_are_inert_defaults():
    body = client.get("/api/v1/schemes").json()
    assert body["variants"]["els_variant"] == "unified_2026"
    assert body["variants"]["women_rebate_enabled"] is False


def test_get_schemes_uny_channel_variants_present():
    body = client.get("/api/v1/schemes").json()
    uny = next(s for s in body["schemes"] if s["scheme_id"] == "NSFDC_UNY")
    assert {v["variant_id"] for v in uny["channel_variants"]} == {"COOP", "SFB"}


# --- GET /schemes/{scheme_id} --------------------------------------------------------

def test_get_scheme_by_id_returns_single_scheme_object():
    r = client.get("/api/v1/schemes/NSFDC_TL")
    assert r.status_code == 200
    body = r.json()
    assert body["scheme_id"] == "NSFDC_TL"
    assert body["moratorium_months_special"] == 12


def test_get_scheme_by_id_unknown_returns_not_found():
    r = client.get("/api/v1/schemes/DOES_NOT_EXIST")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "NOT_FOUND"
    assert r.json()["error"]["field"] == "scheme_id"


# --- GET /meta/activities -----------------------------------------------------------

def test_get_activities_without_query_returns_all():
    r = client.get("/api/v1/meta/activities")
    assert r.status_code == 200
    body = r.json()
    assert len(body["activities"]) >= 40


def test_get_activities_typeahead_matches_activity_code():
    r = client.get("/api/v1/meta/activities", params={"q": "tail"})
    body = r.json()
    codes = {a["activity_code"] for a in body["activities"]}
    assert codes == {"TAILORING"}


def test_get_activities_typeahead_is_case_insensitive():
    r = client.get("/api/v1/meta/activities", params={"q": "DAIRY"})
    body = r.json()
    assert any(a["activity_code"] == "DAIRY_FARMING" for a in body["activities"])


def test_get_activities_no_match_returns_empty_list():
    r = client.get("/api/v1/meta/activities", params={"q": "ZZZZZ_NO_MATCH"})
    assert r.json()["activities"] == []


def test_get_activities_carries_plantation_flag_and_cost_bands():
    r = client.get("/api/v1/meta/activities", params={"q": "HORTICULTURE"})
    activity = r.json()["activities"][0]
    assert set(activity.keys()) == {
        "activity_code", "name_key", "indicative_cost_min", "indicative_cost_max",
        "is_plantation_or_construction",
    }
    assert activity["is_plantation_or_construction"] is True


# --- GET /meta/courses ---------------------------------------------------------------

def test_get_courses_returns_all_recognised_courses():
    r = client.get("/api/v1/meta/courses")
    assert r.status_code == 200
    body = r.json()
    codes = {c["course_code"] for c in body["courses"]}
    assert "BTECH" in codes
    assert len(body["courses"]) >= 24


def test_get_courses_field_shape():
    body = client.get("/api/v1/meta/courses").json()
    course = body["courses"][0]
    assert set(course.keys()) == {"course_code", "name_key", "level", "typical_duration_months"}


# --- GET /meta/documents --------------------------------------------------------------

def test_get_documents_mirrors_recommend_documents_required_shape():
    r = client.get("/api/v1/meta/documents", params={"scheme_id": "NSFDC_MFS"})
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {"documents_required"}
    for doc in body["documents_required"]:
        assert set(doc.keys()) == {"code", "mandatory"}


def test_get_documents_matches_actual_recommend_checklist():
    recommend_body = client.post("/api/v1/recommend", json={
        "locale": "en",
        "profile": {"is_sc": True, "annual_family_income": 240000, "purpose": "business",
                     "activity_code": "TAILORING", "project_cost": 120000},
    }).json()
    documents_body = client.get("/api/v1/meta/documents", params={"scheme_id": "NSFDC_MFS"}).json()
    assert documents_body["documents_required"] == recommend_body["documents_required"]


def test_get_documents_unknown_scheme_returns_not_found():
    r = client.get("/api/v1/meta/documents", params={"scheme_id": "DOES_NOT_EXIST"})
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "NOT_FOUND"


def test_get_documents_els_checklist_differs_from_business_schemes():
    business = client.get("/api/v1/meta/documents", params={"scheme_id": "NSFDC_MFS"}).json()
    education = client.get("/api/v1/meta/documents", params={"scheme_id": "NSFDC_ELS"}).json()
    assert business != education
    els_codes = {d["code"] for d in education["documents_required"]}
    assert "ADMISSION_LETTER" in els_codes


# --- no network / LLM-independent ------------------------------------------------------

def test_reference_endpoints_make_no_network_calls(monkeypatch):
    import socket

    def _blocked(*args, **kwargs):
        raise AssertionError("reference endpoints must not open network sockets")

    monkeypatch.setattr(socket.socket, "connect", _blocked)
    assert client.get("/api/v1/schemes").status_code == 200
    assert client.get("/api/v1/schemes/NSFDC_MFS").status_code == 200
    assert client.get("/api/v1/meta/activities").status_code == 200
    assert client.get("/api/v1/meta/courses").status_code == 200
    assert client.get("/api/v1/meta/documents", params={"scheme_id": "NSFDC_MFS"}).status_code == 200
