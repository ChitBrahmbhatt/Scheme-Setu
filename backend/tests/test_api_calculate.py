"""API tests for POST /calculate (BACKEND_BRIEF.md Step 5)."""
import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app

client = TestClient(app)
URL = "/api/v1/calculate"


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def calc(scheme_id, sanctioned, total_months, mor, channel_variant=None, include_schedule=False):
    return client.post(URL, json={
        "scheme_id": scheme_id,
        "channel_variant": channel_variant,
        "sanctioned_amount": sanctioned,
        "total_period_months": total_months,
        "moratorium_months": mor,
        "include_schedule": include_schedule,
    })


# --- golden cases through the API -----------------------------------------------------

def test_g1_mfs():
    r = calc("NSFDC_MFS", 108000, 36, 3)
    body = r.json()
    assert (body["instalment"], body["total_outgo"], body["total_interest"]) == (10977, 120747, 12747)


def test_g2_amy():
    r = calc("NSFDC_AMY", 108000, 36, 3)
    body = r.json()
    assert (body["instalment"], body["total_outgo"], body["total_interest"]) == (12619, 138809, 30809)


def test_g3_term_loan():
    r = calc("NSFDC_TL", 900000, 84, 6, include_schedule=True)
    body = r.json()
    assert (body["instalment"], body["total_outgo"], body["total_interest"]) == (46518, 1209468, 309468)
    assert body["schedule"][0] == {"n": 1, "due_month": 9, "instalment": 46518, "interest": 18720,
                                    "principal": 27798, "balance": 908202}
    assert body["schedule"][-1]["balance"] == 0


def test_g4_uny_coop_corrected_value():
    r = calc("NSFDC_UNY", 360000, 60, 3, channel_variant="COOP")
    body = r.json()
    assert body["instalment"] == 26527
    assert body["total_outgo"] == 504013
    assert body["total_interest"] == 144013


def test_g5_term_loan_dairy():
    r = calc("NSFDC_TL", 360000, 84, 6)
    body = r.json()
    assert (body["instalment"], body["total_outgo"], body["total_interest"]) == (18607, 483782, 123782)


def test_g6_education_loan():
    r = calc("NSFDC_ELS", 720000, 144, 60)
    body = r.json()
    assert (body["instalment"], body["total_outgo"], body["total_interest"]) == (28777, 1381296, 661296)


def test_g10_plantation_extended_moratorium():
    r = calc("NSFDC_TL", 270000, 84, 12)
    body = r.json()
    assert (body["instalment"], body["total_outgo"], body["total_interest"]) == (15417, 370008, 100008)


# --- arithmetic invariant --------------------------------------------------------------

@pytest.mark.parametrize("scheme_id,sanctioned,total_months,mor,variant", [
    ("NSFDC_MFS", 108000, 36, 3, None),
    ("NSFDC_TL", 900000, 84, 6, None),
    ("NSFDC_UNY", 360000, 60, 3, "COOP"),
    ("NSFDC_ELS", 720000, 144, 60, None),
])
def test_instalment_times_n_equals_total_outgo(scheme_id, sanctioned, total_months, mor, variant):
    body = calc(scheme_id, sanctioned, total_months, mor, channel_variant=variant).json()
    assert body["instalment"] * body["number_of_instalments"] == body["total_outgo"]
    assert body["total_outgo"] - sanctioned == body["total_interest"]


# --- scheme cap validation --------------------------------------------------------------

def test_sanctioned_amount_at_cap_is_accepted():
    r = calc("NSFDC_MFS", 125000, 36, 3)  # exactly loan_max
    assert r.status_code == 200


def test_sanctioned_amount_above_cap_is_rejected():
    r = calc("NSFDC_MFS", 125001, 36, 3)  # loan_max + 1
    assert r.status_code == 400
    body = r.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["field"] == "sanctioned_amount"


def test_total_period_months_above_scheme_cap_is_rejected():
    r = calc("NSFDC_MFS", 100000, 37, 3)  # cap is 36
    assert r.status_code == 400
    assert r.json()["error"]["field"] == "total_period_months"


def test_moratorium_above_scheme_cap_is_rejected():
    r = calc("NSFDC_MFS", 100000, 36, 4)  # cap is 3 (no special moratorium for MFS)
    assert r.status_code == 400
    assert r.json()["error"]["field"] == "moratorium_months"


def test_moratorium_at_tl_special_cap_is_accepted():
    r = calc("NSFDC_TL", 270000, 84, 12)  # 12 is TL's plantation-special cap
    assert r.status_code == 200


def test_moratorium_beyond_tl_special_cap_is_rejected():
    r = calc("NSFDC_TL", 270000, 84, 13)
    assert r.status_code == 400
    assert r.json()["error"]["field"] == "moratorium_months"


# --- invalid scheme / channel variant ---------------------------------------------------

def test_unknown_scheme_id_returns_not_found():
    r = calc("NOT_A_SCHEME", 100000, 36, 3)
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "NOT_FOUND"
    assert r.json()["error"]["field"] == "scheme_id"


def test_uny_without_channel_variant_is_rejected():
    r = calc("NSFDC_UNY", 360000, 60, 3, channel_variant=None)
    assert r.status_code == 400
    assert r.json()["error"]["field"] == "channel_variant"


def test_uny_with_invalid_channel_variant_is_rejected():
    r = calc("NSFDC_UNY", 360000, 60, 3, channel_variant="NOT_A_VARIANT")
    assert r.status_code == 400
    assert r.json()["error"]["field"] == "channel_variant"


def test_non_variant_scheme_with_channel_variant_is_rejected():
    r = calc("NSFDC_MFS", 100000, 36, 3, channel_variant="COOP")
    assert r.status_code == 400
    assert r.json()["error"]["field"] == "channel_variant"


# --- Decimal/integer boundary behaviour ---------------------------------------------------

def test_response_money_fields_are_integers_not_floats():
    body = calc("NSFDC_TL", 900000, 84, 6).json()
    for field in ("sanctioned_amount", "principal_at_repayment_start", "instalment",
                  "monthly_equivalent", "total_outgo", "total_interest"):
        assert isinstance(body[field], int)


def test_zero_or_negative_sanctioned_amount_is_rejected_by_pydantic():
    r = calc("NSFDC_MFS", 0, 36, 3)
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_repayment_period_must_allow_at_least_one_instalment():
    r = calc("NSFDC_MFS", 100000, 36, 36)  # moratorium consumes the entire period
    assert r.status_code == 400


# --- documented validation/error envelope shape -----------------------------------------

def test_missing_required_field_returns_documented_error_envelope():
    r = client.post(URL, json={"scheme_id": "NSFDC_MFS"})
    assert r.status_code == 400
    body = r.json()
    assert set(body["error"].keys()) == {"code", "message", "field"}
    assert body["error"]["code"] == "VALIDATION_ERROR"
