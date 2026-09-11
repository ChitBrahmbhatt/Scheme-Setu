"""Loader and data-integrity tests (BACKEND_BRIEF.md Step 2)."""
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.loader import get_data, load_all, load_i18n, load_partners, load_schemes

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def test_load_all_succeeds_against_real_data_dir():
    data = load_all(DATA_DIR)
    assert len(data.schemes.schemes) == 5
    assert len(data.partners.partners) == 18
    assert len(data.activities.activities) >= 40
    assert len(data.courses.courses) >= 24
    assert set(data.i18n.keys()) == {"en", "hi"}


def test_get_data_is_cached_singleton():
    first = get_data()
    second = get_data()
    assert first is second


# --- schemes.json -----------------------------------------------------------

def test_all_five_scheme_ids_present():
    schemes = load_schemes(DATA_DIR)
    ids = {s.scheme_id for s in schemes.schemes}
    assert ids == {"NSFDC_MFS", "NSFDC_TL", "NSFDC_AMY", "NSFDC_UNY", "NSFDC_ELS"}


def test_every_scheme_field_carries_verified_data_tier():
    schemes = load_schemes(DATA_DIR)
    for scheme in schemes.schemes:
        assert scheme.data_tier == "VERIFIED"
        assert len(scheme.citations) > 0
        for citation in scheme.citations:
            assert citation.source_url.startswith("https://nsfdc.nic.in")
            assert citation.as_of


def test_uny_has_exactly_two_channel_variants_coop_and_sfb():
    schemes = load_schemes(DATA_DIR)
    uny = next(s for s in schemes.schemes if s.scheme_id == "NSFDC_UNY")
    assert uny.interest_rate is None
    assert uny.channel_types is None
    variant_ids = {v.variant_id for v in uny.channel_variants}
    assert variant_ids == {"COOP", "SFB"}
    rates = {v.variant_id: v.interest_rate for v in uny.channel_variants}
    assert rates == {"COOP": 13.0, "SFB": 15.0}


def test_els_excludes_moratorium_from_tenure():
    schemes = load_schemes(DATA_DIR)
    els = next(s for s in schemes.schemes if s.scheme_id == "NSFDC_ELS")
    assert els.tenure_includes_moratorium is False
    assert els.purpose == "education"
    assert els.total_period_months == 144


def test_tl_has_plantation_special_moratorium():
    schemes = load_schemes(DATA_DIR)
    tl = next(s for s in schemes.schemes if s.scheme_id == "NSFDC_TL")
    assert tl.moratorium_months == 6
    assert tl.moratorium_months_special == 12


def test_els_variant_defaults_off_and_alternatives_are_variant_tier():
    schemes = load_schemes(DATA_DIR)
    assert schemes.variants["els_variant"] == "unified_2026"
    assert schemes.variants["women_rebate_enabled"] is False
    alt = schemes.variant_alternatives  # extra field, allowed
    assert alt["els_variant"]["split_legacy"]["data_tier"] == "VARIANT"
    assert alt["women_rebate_enabled"]["true"]["data_tier"] == "VARIANT"


def test_eligibility_income_ceiling_is_verified():
    schemes = load_schemes(DATA_DIR)
    assert schemes.eligibility["income_ceiling"] == 500000
    assert schemes.eligibility["data_tier"] == "VERIFIED"


def test_malformed_schemes_file_fails_loudly(tmp_path):
    bad = json.loads((DATA_DIR / "schemes.json").read_text())
    del bad["schemes"][0]["interest_rate"]  # now neither rate nor variants -> invalid
    (tmp_path / "schemes.json").write_text(json.dumps(bad))
    with pytest.raises(ValidationError):
        load_schemes(tmp_path)


def test_missing_data_file_fails_loudly(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_schemes(tmp_path)


# --- partners.json -----------------------------------------------------------

def test_exactly_eighteen_partners_all_simulated():
    partners = load_partners(DATA_DIR)
    assert len(partners.partners) == 18
    assert partners.data_tier == "SIMULATED"
    for p in partners.partners:
        assert p.data_tier == "SIMULATED"


def test_partner_ids_are_unique():
    partners = load_partners(DATA_DIR)
    ids = [p.partner_id for p in partners.partners]
    assert len(ids) == len(set(ids))


def test_at_least_two_partners_would_be_not_accepting():
    """Per CLAUDE.md §6: NOT_ACCEPTING when overdue_ratio_pct > 25 or
    fund_utilisation_pct >= 100. Two records must trigger this."""
    partners = load_partners(DATA_DIR)
    not_accepting = [
        p for p in partners.partners
        if p.overdue_ratio_pct > 25 or p.fund_utilisation_pct >= 100
    ]
    assert len(not_accepting) >= 2


def test_district_distribution_matches_claude_md():
    partners = load_partners(DATA_DIR)
    ahmedabad = [p for p in partners.partners if p.district == "Ahmedabad"]
    dahod = [p for p in partners.partners if p.district == "Dahod"]
    other_state = [p for p in partners.partners if p.state_code != "GJ"]
    assert len(ahmedabad) == 10  # 8 baseline + 2 deliberately NOT_ACCEPTING
    assert len(dahod) == 6
    assert len(other_state) == 2


def test_all_channel_types_represented_in_ahmedabad():
    partners = load_partners(DATA_DIR)
    ahmedabad_types = {p.type for p in partners.partners if p.district == "Ahmedabad"}
    assert {"SCA", "PSB", "RRB", "NBFC_MFI", "COOP_BANK", "COOP_SOCIETY", "SFB"} <= ahmedabad_types


def test_channel_type_scheme_support_is_consistent():
    partners = load_partners(DATA_DIR)
    expectations = {
        "SCA": {"NSFDC_MFS", "NSFDC_TL", "NSFDC_ELS"},
        "PSB": {"NSFDC_MFS", "NSFDC_TL", "NSFDC_ELS"},
        "RRB": {"NSFDC_MFS", "NSFDC_TL", "NSFDC_ELS"},
        "NBFC_MFI": {"NSFDC_AMY"},
        "COOP_BANK": {"NSFDC_UNY"},
        "COOP_SOCIETY": {"NSFDC_UNY"},
        "SFB": {"NSFDC_UNY"},
    }
    for p in partners.partners:
        assert set(p.schemes_supported) == expectations[p.type]


# --- activities / courses / documents -----------------------------------------

def test_activities_include_tailoring_and_dairy_with_matching_cost_bands():
    from app.loader import load_activities
    activities = load_activities(DATA_DIR)
    by_code = {a.activity_code: a for a in activities.activities}
    assert "TAILORING" in by_code
    assert by_code["TAILORING"].indicative_cost_min <= 120000 <= by_code["TAILORING"].indicative_cost_max
    assert "DAIRY_FARMING" in by_code
    assert by_code["DAIRY_FARMING"].indicative_cost_min <= 400000 <= by_code["DAIRY_FARMING"].indicative_cost_max


def test_at_least_one_plantation_or_construction_activity():
    from app.loader import load_activities
    activities = load_activities(DATA_DIR)
    flagged = [a for a in activities.activities if a.is_plantation_or_construction]
    assert len(flagged) >= 1


def test_courses_include_btech():
    from app.loader import load_courses
    courses = load_courses(DATA_DIR)
    codes = {c.course_code for c in courses.courses}
    assert "BTECH" in codes


def test_documents_checklists_cover_all_five_schemes():
    from app.loader import load_documents
    documents = load_documents(DATA_DIR)
    assert set(documents.checklists.keys()) == {
        "NSFDC_MFS", "NSFDC_TL", "NSFDC_AMY", "NSFDC_UNY", "NSFDC_ELS",
    }
    known_codes = {d.code for d in documents.documents}
    for scheme_id, items in documents.checklists.items():
        for item in items:
            assert item.code in known_codes


# --- i18n ---------------------------------------------------------------------

def test_i18n_en_and_hi_have_identical_key_sets():
    bundles = load_i18n(DATA_DIR)
    assert set(bundles["en"].root.keys()) == set(bundles["hi"].root.keys())


def test_i18n_covers_every_reason_and_routing_code():
    bundles = load_i18n(DATA_DIR)
    en_keys = bundles["en"].root.keys()
    reason_codes = [
        "NOT_SC", "INCOME_ABOVE_CEILING", "MEMBER_NOT_SC", "MEMBER_INCOME_ABOVE_CEILING",
        "COST_ABOVE_ALL_CAPS", "NO_ADMISSION_CONFIRMED", "COURSE_NOT_RECOGNISED",
        "COST_WITHIN_MFS_CAP", "COST_REQUIRES_TERM_LOAN", "COST_WITHIN_UNY_CAP",
        "INCOME_WITHIN_CEILING", "LOWEST_COST_OPTION", "ELIGIBLE_BUT_COSTLIER",
        "PLANTATION_EXTENDED_MORATORIUM", "SANCTION_AT_PARTNER_DISCRETION",
        "FIGURES_ARE_INDICATIVE", "MORATORIUM_TREATMENT_ASSUMED", "CHECK_NBCFDC",
        "REAPPLY_IF_INCOME_CHANGES",
    ]
    for code in reason_codes:
        assert f"reason.{code}" in en_keys

    routing_codes = [
        "UTILISATION_WITHIN_LIMIT", "UTILISATION_HIGH", "UTILISATION_EXHAUSTED",
        "OVERDUE_BELOW_THRESHOLD", "OVERDUE_ELEVATED", "OVERDUE_ABOVE_THRESHOLD",
        "SCHEME_NOT_SUPPORTED",
    ]
    for code in routing_codes:
        assert f"routing.{code}" in en_keys


def test_i18n_bundle_with_mismatched_keys_fails_loudly(tmp_path):
    (tmp_path / "i18n").mkdir()
    (tmp_path / "i18n" / "en.json").write_text(json.dumps({"a": "1", "b": "2"}))
    (tmp_path / "i18n" / "hi.json").write_text(json.dumps({"a": "1"}))
    with pytest.raises(ValueError):
        load_i18n(tmp_path)
