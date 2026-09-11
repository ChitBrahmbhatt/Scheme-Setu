"""API tests for POST /recommend (BACKEND_BRIEF.md Step 5)."""
import os

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app

client = TestClient(app)
URL = "/api/v1/recommend"


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def business(cost, income=240000, is_sc=True, applicant_type="individual", members=None, activity_code="TAILORING"):
    profile = {
        "applicant_type": applicant_type,
        "is_sc": is_sc,
        "annual_family_income": income,
        "purpose": "business",
        "activity_code": activity_code,
        "project_cost": cost,
    }
    if members is not None:
        profile["members"] = members
    return {"locale": "en", "profile": profile}


def education(fee, remaining_months=48, income=240000, is_sc=True, course_code="BTECH", admission_confirmed=True):
    return {
        "locale": "en",
        "profile": {
            "is_sc": is_sc,
            "annual_family_income": income,
            "purpose": "education",
            "education": {
                "course_code": course_code,
                "study_location": "india",
                "total_course_fee": fee,
                "remaining_course_months": remaining_months,
                "admission_confirmed": admission_confirmed,
            },
        },
    }


def option_ids(body):
    return [o["option_id"] for o in body["options"]]


# --- valid recommendations -------------------------------------------------------

def test_valid_mfs_recommendation_matches_g1():
    r = client.post(URL, json=business(120000))
    assert r.status_code == 200
    body = r.json()
    assert body["eligible"] is True
    mfs = next(o for o in body["options"] if o["option_id"] == "NSFDC_MFS")
    assert mfs["rank"] == 1
    assert mfs["sanctionable_amount"] == 108000
    assert mfs["own_contribution_required"] == 12000
    assert mfs["instalment"] == 10977
    assert mfs["total_outgo"] == 120747
    assert mfs["total_interest"] == 12747
    assert mfs["number_of_instalments"] == 11
    assert {r["code"] for r in mfs["reasons"]} == {"COST_WITHIN_MFS_CAP", "INCOME_WITHIN_CEILING", "LOWEST_COST_OPTION"}


def test_valid_amy_recommendation_present_and_costlier():
    r = client.post(URL, json=business(120000))
    body = r.json()
    amy = next(o for o in body["options"] if o["option_id"] == "NSFDC_AMY")
    assert amy["instalment"] == 12619
    assert amy["total_outgo"] == 138809
    assert amy["total_interest"] == 30809
    assert amy["reasons"] == [{"code": "ELIGIBLE_BUT_COSTLIER", "params": {"delta": 18062}}]


def test_project_cost_140000_overlap_all_four_options_reach_ranking():
    r = client.post(URL, json=business(140000))
    body = r.json()
    assert body["eligible"] is True
    assert set(option_ids(body)) == {"NSFDC_MFS", "NSFDC_AMY", "NSFDC_UNY.COOP", "NSFDC_UNY.SFB"}


def test_project_cost_140001_mfs_amy_disappear_tl_uny_apply():
    r = client.post(URL, json=business(140001))
    body = r.json()
    assert body["eligible"] is True
    assert set(option_ids(body)) == {"NSFDC_TL", "NSFDC_UNY.COOP", "NSFDC_UNY.SFB"}
    tl = next(o for o in body["options"] if o["option_id"] == "NSFDC_TL")
    assert tl["sanctionable_amount"] == 126001


def test_uny_upper_boundary_500000():
    at_cap = client.post(URL, json=business(500000)).json()
    assert "NSFDC_UNY.COOP" in option_ids(at_cap)

    over_cap = client.post(URL, json=business(500001)).json()
    assert "NSFDC_UNY.COOP" not in option_ids(over_cap)
    assert "NSFDC_TL" in option_ids(over_cap)


def test_project_cost_above_50_lakh_is_ineligible_blocker_shaped():
    r = client.post(URL, json=business(5000001))
    body = r.json()
    assert r.status_code == 200
    assert body["eligible"] is False
    assert body["options"] == []
    assert body["comparison"] is None
    assert body["blockers"][0]["code"] == "COST_ABOVE_ALL_CAPS"


# --- blockers ----------------------------------------------------------------------

def test_not_sc_returns_200_ineligible():
    r = client.post(URL, json=business(120000, is_sc=False))
    assert r.status_code == 200
    body = r.json()
    assert body["eligible"] is False
    assert body["blockers"][0]["code"] == "NOT_SC"
    assert {rr["code"] for rr in body["remediation"]} == {"CHECK_NBCFDC", "REAPPLY_IF_INCOME_CHANGES"}


def test_income_exactly_500000_is_eligible():
    r = client.post(URL, json=business(120000, income=500000))
    body = r.json()
    assert body["eligible"] is True


def test_income_above_500000_is_blocked_matches_g7():
    r = client.post(URL, json=business(120000, income=650000))
    body = r.json()
    assert r.status_code == 200
    assert body["eligible"] is False
    assert body["blockers"] == [{"code": "INCOME_ABOVE_CEILING", "params": {"provided": 650000, "ceiling": 500000}}]
    assert body["comparison"] is None
    assert body["documents_required"] == []
    assert body["next_step"] is None


def test_partnership_member_not_sc_blocks():
    r = client.post(URL, json=business(
        120000, applicant_type="partnership",
        members=[{"is_sc": True, "annual_family_income": 100000},
                 {"is_sc": False, "annual_family_income": 100000}],
    ))
    body = r.json()
    assert body["eligible"] is False
    assert any(b["code"] == "MEMBER_NOT_SC" for b in body["blockers"])


def test_cooperative_society_member_income_blocks():
    r = client.post(URL, json=business(
        120000, applicant_type="cooperative_society",
        members=[{"is_sc": True, "annual_family_income": 600000}],
    ))
    body = r.json()
    assert body["eligible"] is False
    assert any(b["code"] == "MEMBER_INCOME_ABOVE_CEILING" for b in body["blockers"])


# --- education -----------------------------------------------------------------------

def test_education_recognised_course_and_admission_confirmed():
    r = client.post(URL, json=education(800000, remaining_months=48))
    body = r.json()
    assert body["eligible"] is True
    els = body["options"][0]
    assert els["option_id"] == "NSFDC_ELS"
    assert els["instalment"] == 28777
    assert els["total_outgo"] == 1381296
    assert els["total_interest"] == 661296
    assert els["moratorium_months"] == 60


def test_education_without_admission_confirmed_blocked():
    r = client.post(URL, json=education(800000, admission_confirmed=False))
    body = r.json()
    assert body["eligible"] is False
    assert body["blockers"][0]["code"] == "NO_ADMISSION_CONFIRMED"


def test_education_unrecognised_course_blocked():
    r = client.post(URL, json=education(800000, course_code="ASTROLOGY_DIPLOMA"))
    body = r.json()
    assert body["eligible"] is False
    assert body["blockers"][0]["code"] == "COURSE_NOT_RECOGNISED"


# --- ranking / comparison passthrough -------------------------------------------------

def test_recommendation_ordering_follows_ranking_and_all_options_returned():
    r = client.post(URL, json=business(400000))
    body = r.json()
    assert option_ids(body) == ["NSFDC_TL", "NSFDC_UNY.COOP", "NSFDC_UNY.SFB"]
    assert [o["rank"] for o in body["options"]] == [1, 2, 3]
    assert len(body["options"]) == 3


def test_recommended_option_id_matches_rank_1():
    r = client.post(URL, json=business(400000))
    body = r.json()
    assert body["options"][0]["rank"] == 1
    assert body["comparison"]["cheapest_option_id"] == body["options"][0]["option_id"]


def test_comparison_object_is_correct_for_dairy_project():
    r = client.post(URL, json=business(400000))
    body = r.json()
    comparison = body["comparison"]
    assert comparison["cheapest_option_id"] == "NSFDC_TL"
    assert comparison["costliest_option_id"] == "NSFDC_UNY.SFB"
    assert comparison["extra_cost_if_worst_route"] == 168903 - 123782
    assert comparison["message_key"] == "comparison.route_matters"


def test_reason_codes_and_params_are_preserved_end_to_end():
    r = client.post(URL, json=business(300000, activity_code="HORTICULTURE_PLANTATION"))
    body = r.json()
    tl = next(o for o in body["options"] if o["option_id"] == "NSFDC_TL")
    codes = {rr["code"] for rr in tl["reasons"]}
    assert "PLANTATION_EXTENDED_MORATORIUM" in codes or tl["moratorium_months"] == 12
    assert tl["moratorium_months"] == 12


# --- VARIANT stays inert / LLM disabled / no network ------------------------------------

def test_variant_alternatives_stay_disabled_by_default():
    r = client.post(URL, json=education(800000))
    body = r.json()
    ids = option_ids(body)
    assert all("split_legacy" not in i and "women_rebate" not in i for i in ids)
    els = body["options"][0]
    assert els["interest_rate"] == 6.5  # unified_2026 default, not split_legacy


def test_llm_disabled_env_still_serves_recommend(monkeypatch):
    monkeypatch.setenv("LLM_ENABLED", "false")
    get_settings.cache_clear()
    r = client.post(URL, json=business(120000))
    assert r.status_code == 200
    assert r.json()["eligible"] is True


def test_recommend_makes_no_network_calls(monkeypatch):
    import socket

    def _blocked(*args, **kwargs):
        raise AssertionError("recommend must not open network sockets")

    monkeypatch.setattr(socket.socket, "connect", _blocked)
    r = client.post(URL, json=business(120000))
    assert r.status_code == 200


# --- validation errors ----------------------------------------------------------------

def test_missing_required_field_returns_validation_error():
    r = client.post(URL, json={"locale": "en", "profile": {"purpose": "business"}})
    assert r.status_code == 400
    body = r.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"


def test_business_purpose_without_project_cost_is_rejected():
    r = client.post(URL, json={
        "locale": "en",
        "profile": {"is_sc": True, "annual_family_income": 200000, "purpose": "business",
                     "activity_code": "TAILORING"},
    })
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"
