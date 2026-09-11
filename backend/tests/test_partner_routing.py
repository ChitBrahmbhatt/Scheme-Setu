"""Partner filtering/routing/ordering tests (CLAUDE.md §6, BACKEND_BRIEF.md Step 6)."""
from pathlib import Path

from app.data_models import Partner
from app.engine.partner_routing import base_scheme_id, classify, filter_by_scheme, locate, sort_and_split
from app.loader import load_all

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
DATA = load_all(DATA_DIR)
PARTNERS = DATA.partners.partners

AHMEDABAD_LAT, AHMEDABAD_LNG = 23.0225, 72.5714


def make_partner(partner_id, lat, lng, overdue_ratio_pct, fund_utilisation_pct,
                  schemes_supported=("NSFDC_MFS",), district="Ahmedabad", state_code="GJ"):
    return Partner(
        partner_id=partner_id,
        name=f"Test Partner {partner_id}",
        branch_label="Test Branch",
        type="SCA",
        address="Test Address",
        district=district,
        state="Gujarat",
        state_code=state_code,
        pincode="380001",
        lat=lat,
        lng=lng,
        phone="000-0000",
        schemes_supported=list(schemes_supported),
        fund_utilisation_pct=fund_utilisation_pct,
        overdue_ratio_pct=overdue_ratio_pct,
        avg_sanction_days=20,
        data_tier="SIMULATED",
    )


# --- scheme filtering ------------------------------------------------------------

def test_supported_scheme_appears():
    result = filter_by_scheme(PARTNERS, "NSFDC_MFS")
    assert any(p.partner_id == "SCA-GJ-AHM-01" for p in result)


def test_unsupported_scheme_is_excluded():
    result = filter_by_scheme(PARTNERS, "NSFDC_AMY")
    assert all("NSFDC_AMY" in p.schemes_supported for p in result)
    assert not any(p.partner_id == "SCA-GJ-AHM-01" for p in result)  # SCA doesn't support AMY


def test_uny_variant_scheme_id_resolves_to_base_scheme():
    assert base_scheme_id("NSFDC_UNY.SFB") == "NSFDC_UNY"
    result = filter_by_scheme(PARTNERS, "NSFDC_UNY.SFB")
    assert all("NSFDC_UNY" in p.schemes_supported for p in result)
    assert len(result) > 0


def test_filtering_happens_before_ranking_unsupported_never_enters_located_list():
    located = locate(PARTNERS, "NSFDC_AMY", AHMEDABAD_LAT, AHMEDABAD_LNG, radius_km=100)
    main, excluded = sort_and_split(located)
    all_ids = {lp.partner.partner_id for lp in main + excluded}
    assert "SCA-GJ-AHM-01" not in all_ids  # SCA does not support AMY regardless of proximity


# --- radius -----------------------------------------------------------------------

def test_partner_just_inside_radius_is_included():
    near = make_partner("NEAR", AHMEDABAD_LAT + 0.001, AHMEDABAD_LNG, 5, 50)
    located = locate([near], "NSFDC_MFS", AHMEDABAD_LAT, AHMEDABAD_LNG, radius_km=1)
    assert len(located) == 1


def test_partner_just_outside_radius_is_excluded_entirely():
    far = make_partner("FAR", AHMEDABAD_LAT + 5.0, AHMEDABAD_LNG, 5, 50)
    located = locate([far], "NSFDC_MFS", AHMEDABAD_LAT, AHMEDABAD_LNG, radius_km=1)
    assert located == []


def test_default_radius_used_when_none_supplied_at_engine_level():
    # engine.locate takes an explicit radius; "no radius" here means "no cap"
    far = make_partner("FAR", AHMEDABAD_LAT + 5.0, AHMEDABAD_LNG, 5, 50)
    located = locate([far], "NSFDC_MFS", AHMEDABAD_LAT, AHMEDABAD_LNG, radius_km=None)
    assert len(located) == 1  # no radius cap = included regardless of distance


def test_custom_radius_changes_inclusion():
    partner = make_partner("P", AHMEDABAD_LAT + 0.02, AHMEDABAD_LNG, 5, 50)  # ~2.2 km away
    tight = locate([partner], "NSFDC_MFS", AHMEDABAD_LAT, AHMEDABAD_LNG, radius_km=1)
    loose = locate([partner], "NSFDC_MFS", AHMEDABAD_LAT, AHMEDABAD_LNG, radius_km=10)
    assert tight == []
    assert len(loose) == 1


def test_no_partners_within_radius_yields_empty_list_not_fabricated():
    located = locate(PARTNERS, "NSFDC_MFS", 1.0, 1.0, radius_km=5)  # middle of nowhere
    assert located == []


# --- routing boundaries (CLAUDE.md §6, confirmed exclusive lower bound at 15) --------

def test_overdue_14_is_accepting():
    assert classify(overdue_ratio_pct=14, fund_utilisation_pct=50).status == "ACCEPTING"


def test_overdue_15_is_accepting_exclusive_lower_bound():
    assert classify(overdue_ratio_pct=15, fund_utilisation_pct=50).status == "ACCEPTING"


def test_overdue_just_above_15_is_limited():
    assert classify(overdue_ratio_pct=15.01, fund_utilisation_pct=50).status == "LIMITED"


def test_overdue_25_is_limited():
    assert classify(overdue_ratio_pct=25, fund_utilisation_pct=50).status == "LIMITED"


def test_overdue_26_is_not_accepting():
    assert classify(overdue_ratio_pct=26, fund_utilisation_pct=50).status == "NOT_ACCEPTING"


def test_utilisation_84_99_is_accepting():
    assert classify(overdue_ratio_pct=5, fund_utilisation_pct=84.99).status == "ACCEPTING"


def test_utilisation_85_is_limited():
    assert classify(overdue_ratio_pct=5, fund_utilisation_pct=85).status == "LIMITED"


def test_utilisation_99_99_is_limited():
    assert classify(overdue_ratio_pct=5, fund_utilisation_pct=99.99).status == "LIMITED"


def test_utilisation_100_is_not_accepting():
    assert classify(overdue_ratio_pct=5, fund_utilisation_pct=100).status == "NOT_ACCEPTING"


def test_mixed_indicators_more_restrictive_status_wins():
    # overdue says ACCEPTING (14), utilisation says NOT_ACCEPTING (100)
    result = classify(overdue_ratio_pct=14, fund_utilisation_pct=100)
    assert result.status == "NOT_ACCEPTING"
    codes = {r.code for r in result.reasons}
    assert "UTILISATION_EXHAUSTED" in codes
    assert "OVERDUE_BELOW_THRESHOLD" in codes

    # overdue says LIMITED (20), utilisation says ACCEPTING (10)
    result2 = classify(overdue_ratio_pct=20, fund_utilisation_pct=10)
    assert result2.status == "LIMITED"


# --- ordering -----------------------------------------------------------------------

def test_accepting_sorts_before_limited_regardless_of_distance():
    limited_near = make_partner("LIM_NEAR", AHMEDABAD_LAT + 0.001, AHMEDABAD_LNG, 20, 50)  # LIMITED, very close
    accepting_far = make_partner("ACC_FAR", AHMEDABAD_LAT + 0.05, AHMEDABAD_LNG, 5, 50)     # ACCEPTING, farther
    located = locate([limited_near, accepting_far], "NSFDC_MFS", AHMEDABAD_LAT, AHMEDABAD_LNG, radius_km=50)
    main, _ = sort_and_split(located)
    assert [lp.partner.partner_id for lp in main] == ["ACC_FAR", "LIM_NEAR"]


def test_nearest_accepting_first():
    far = make_partner("FAR", AHMEDABAD_LAT + 0.05, AHMEDABAD_LNG, 5, 50)
    near = make_partner("NEAR", AHMEDABAD_LAT + 0.005, AHMEDABAD_LNG, 5, 50)
    located = locate([far, near], "NSFDC_MFS", AHMEDABAD_LAT, AHMEDABAD_LNG, radius_km=50)
    main, _ = sort_and_split(located)
    assert [lp.partner.partner_id for lp in main] == ["NEAR", "FAR"]


def test_nearest_limited_first():
    far = make_partner("FAR", AHMEDABAD_LAT + 0.05, AHMEDABAD_LNG, 20, 50)
    near = make_partner("NEAR", AHMEDABAD_LAT + 0.005, AHMEDABAD_LNG, 20, 50)
    located = locate([far, near], "NSFDC_MFS", AHMEDABAD_LAT, AHMEDABAD_LNG, radius_km=50)
    main, _ = sort_and_split(located)
    assert [lp.partner.partner_id for lp in main] == ["NEAR", "FAR"]


def test_deterministic_tie_behavior_preserves_input_order():
    a = make_partner("A", AHMEDABAD_LAT + 0.001, AHMEDABAD_LNG, 5, 50)
    b = make_partner("B", AHMEDABAD_LAT + 0.001, AHMEDABAD_LNG, 5, 50)  # identical distance/status
    order_ab = sort_and_split(locate([a, b], "NSFDC_MFS", AHMEDABAD_LAT, AHMEDABAD_LNG, radius_km=50))[0]
    order_ba = sort_and_split(locate([b, a], "NSFDC_MFS", AHMEDABAD_LAT, AHMEDABAD_LNG, radius_km=50))[0]
    assert [lp.partner.partner_id for lp in order_ab] == ["A", "B"]
    assert [lp.partner.partner_id for lp in order_ba] == ["B", "A"]


def test_not_accepting_excluded_from_main_results():
    blocked = make_partner("BLOCKED", AHMEDABAD_LAT + 0.001, AHMEDABAD_LNG, 30, 50)
    accepting = make_partner("OK", AHMEDABAD_LAT + 0.001, AHMEDABAD_LNG, 5, 50)
    located = locate([blocked, accepting], "NSFDC_MFS", AHMEDABAD_LAT, AHMEDABAD_LNG, radius_km=50)
    main, excluded = sort_and_split(located)
    assert [lp.partner.partner_id for lp in main] == ["OK"]
    assert [lp.partner.partner_id for lp in excluded] == ["BLOCKED"]


# --- real dataset sanity check -------------------------------------------------------

def test_real_dataset_ahmedabad_mfs_has_at_least_two_not_accepting_nearby():
    located = locate(PARTNERS, "NSFDC_AMY", AHMEDABAD_LAT, AHMEDABAD_LNG, radius_km=25)
    main, excluded = sort_and_split(located)
    assert any(lp.partner.partner_id == "MFI-GJ-AHM-09" for lp in excluded)
