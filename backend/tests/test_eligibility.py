"""Eligibility engine tests (CLAUDE.md §5, BACKEND_BRIEF.md Step 3)."""
from pathlib import Path

import pytest

from app.engine.eligibility import EducationProfile, Member, Profile, evaluate
from app.loader import load_all

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
DATA = load_all(DATA_DIR)
SCHEMES = DATA.schemes
COURSE_CODES = frozenset(c.course_code for c in DATA.courses.courses)


def business_profile(project_cost, income=240000, is_sc=True, **kwargs):
    return Profile(
        is_sc=is_sc,
        annual_family_income=income,
        purpose="business",
        project_cost=project_cost,
        **kwargs,
    )


def education_profile(fee, remaining_months=48, income=240000, is_sc=True,
                       course_code="BTECH", admission_confirmed=True):
    return Profile(
        is_sc=is_sc,
        annual_family_income=income,
        purpose="education",
        education=EducationProfile(
            course_code=course_code,
            study_location="india",
            total_course_fee=fee,
            remaining_course_months=remaining_months,
            admission_confirmed=admission_confirmed,
        ),
    )


def option_ids(result):
    return {o.option_id for o in result.options}


# --- hard blockers ------------------------------------------------------------

def test_not_sc_blocks_and_short_circuits():
    result = evaluate(business_profile(120000, is_sc=False), SCHEMES, COURSE_CODES)
    assert result.eligible is False
    assert result.options == []
    assert [b.code for b in result.blockers] == ["NOT_SC"]
    assert {r.code for r in result.remediation} == {"CHECK_NBCFDC", "REAPPLY_IF_INCOME_CHANGES"}


def test_income_above_ceiling_blocks():
    result = evaluate(business_profile(120000, income=650000), SCHEMES, COURSE_CODES)
    assert result.eligible is False
    assert result.options == []
    blocker = result.blockers[0]
    assert blocker.code == "INCOME_ABOVE_CEILING"
    assert blocker.params == {"provided": 650000, "ceiling": 500000}


def test_income_exactly_at_ceiling_is_eligible():
    result = evaluate(business_profile(120000, income=500000), SCHEMES, COURSE_CODES)
    assert result.eligible is True
    assert "NSFDC_MFS" in option_ids(result)


def test_income_one_rupee_above_ceiling_is_blocked():
    result = evaluate(business_profile(120000, income=500001), SCHEMES, COURSE_CODES)
    assert result.eligible is False
    assert result.blockers[0].code == "INCOME_ABOVE_CEILING"
    assert result.blockers[0].params["provided"] == 500001


def test_partnership_member_not_sc_blocks():
    profile = business_profile(
        120000,
        applicant_type="partnership",
        members=(Member(is_sc=True, annual_family_income=100000),
                  Member(is_sc=False, annual_family_income=100000)),
    )
    result = evaluate(profile, SCHEMES, COURSE_CODES)
    assert result.eligible is False
    codes = [b.code for b in result.blockers]
    assert "MEMBER_NOT_SC" in codes


def test_cooperative_society_member_income_above_ceiling_blocks():
    profile = business_profile(
        120000,
        applicant_type="cooperative_society",
        members=(Member(is_sc=True, annual_family_income=600000),),
    )
    result = evaluate(profile, SCHEMES, COURSE_CODES)
    assert result.eligible is False
    blocker = next(b for b in result.blockers if b.code == "MEMBER_INCOME_ABOVE_CEILING")
    assert blocker.params["provided"] == 600000
    assert blocker.params["ceiling"] == 500000


def test_partnership_all_members_sc_and_within_ceiling_is_eligible():
    profile = business_profile(
        120000,
        applicant_type="partnership",
        members=(Member(is_sc=True, annual_family_income=100000),
                  Member(is_sc=True, annual_family_income=200000)),
    )
    result = evaluate(profile, SCHEMES, COURSE_CODES)
    assert result.eligible is True


# --- project cost boundaries ---------------------------------------------------

def test_project_cost_140000_boundary_mfs_amy_uny_apply_not_tl():
    result = evaluate(business_profile(140000), SCHEMES, COURSE_CODES)
    assert result.eligible is True
    ids = option_ids(result)
    assert "NSFDC_MFS" in ids
    assert "NSFDC_AMY" in ids
    assert "NSFDC_UNY.COOP" in ids
    assert "NSFDC_UNY.SFB" in ids
    assert "NSFDC_TL" not in ids


def test_project_cost_140001_boundary_tl_uny_apply_not_mfs_amy():
    result = evaluate(business_profile(140001), SCHEMES, COURSE_CODES)
    assert result.eligible is True
    ids = option_ids(result)
    assert "NSFDC_TL" in ids
    assert "NSFDC_UNY.COOP" in ids
    assert "NSFDC_UNY.SFB" in ids
    assert "NSFDC_MFS" not in ids
    assert "NSFDC_AMY" not in ids


def test_uny_upper_boundary_500000_applies_500001_does_not():
    at_cap = evaluate(business_profile(500000), SCHEMES, COURSE_CODES)
    assert "NSFDC_UNY.COOP" in option_ids(at_cap)
    over_cap = evaluate(business_profile(500001), SCHEMES, COURSE_CODES)
    assert "NSFDC_UNY.COOP" not in option_ids(over_cap)
    assert "NSFDC_UNY.SFB" not in option_ids(over_cap)
    # Term Loan still applies at 500001 (well within its 5,000,000 cap)
    assert "NSFDC_TL" in option_ids(over_cap)


def test_term_loan_upper_boundary_5000000_applies_5000001_blocked():
    at_cap = evaluate(business_profile(5000000), SCHEMES, COURSE_CODES)
    assert "NSFDC_TL" in option_ids(at_cap)
    assert at_cap.eligible is True

    over_cap = evaluate(business_profile(5000001), SCHEMES, COURSE_CODES)
    assert over_cap.eligible is False
    assert over_cap.blockers[0].code == "COST_ABOVE_ALL_CAPS"


def test_g8_boundary_matches_claude_md_narrative():
    """CLAUDE.md G8: 140000 -> MFS/AMY/UNY eligible, TL not;
    140001 -> TL/UNY only."""
    lower = evaluate(business_profile(140000), SCHEMES, COURSE_CODES)
    upper = evaluate(business_profile(140001), SCHEMES, COURSE_CODES)
    assert option_ids(lower) == {"NSFDC_MFS", "NSFDC_AMY", "NSFDC_UNY.COOP", "NSFDC_UNY.SFB"}
    assert option_ids(upper) == {"NSFDC_TL", "NSFDC_UNY.COOP", "NSFDC_UNY.SFB"}


# --- Term Loan minimum enforcement ---------------------------------------------

def test_term_loan_minimum_is_never_breached_at_its_own_cost_floor():
    """At the cost floor just above the MFS/AMY cap, the 90% sanction must
    clear the Term Loan's ₹1,25,000 floor (documented as an explicit
    enforcement, even though the cost boundary makes it structurally true)."""
    result = evaluate(business_profile(140001), SCHEMES, COURSE_CODES)
    tl_option = next(o for o in result.options if o.option_id == "NSFDC_TL")
    assert tl_option.sanctionable_amount == 126001
    assert tl_option.sanctionable_amount > 125000


def test_term_loan_minimum_enforcement_actually_excludes_when_breached():
    """Directly exercise the loan_min guard with a scheme config mutated to
    make the 90% sanction fall below the floor, proving the enforcement
    branch is real rather than permanently unreachable."""
    from dataclasses import replace as dc_replace

    schemes = SCHEMES
    tl = next(s for s in schemes.schemes if s.scheme_id == "NSFDC_TL")
    # Force sanction (90% of 140001) below an artificially raised loan_min.
    mutated_tl = tl.model_copy(update={"loan_min": 200000})
    mutated_schemes = schemes.model_copy(
        update={"schemes": [mutated_tl if s.scheme_id == "NSFDC_TL" else s for s in schemes.schemes]}
    )
    result = evaluate(business_profile(140001), mutated_schemes, COURSE_CODES)
    assert "NSFDC_TL" not in option_ids(result)


# --- sanctionable amount / own contribution ------------------------------------

def test_g1_sanctionable_amount_and_own_contribution():
    result = evaluate(business_profile(120000), SCHEMES, COURSE_CODES)
    mfs = next(o for o in result.options if o.option_id == "NSFDC_MFS")
    assert mfs.sanctionable_amount == 108000
    assert mfs.own_contribution_required == 12000


def test_g4_dairy_sanctionable_amount_and_own_contribution_all_options():
    result = evaluate(business_profile(400000), SCHEMES, COURSE_CODES)
    for option in result.options:
        assert option.sanctionable_amount == 360000
        assert option.own_contribution_required == 40000


def test_g3_term_loan_only_sanctionable_amount():
    result = evaluate(business_profile(1000000), SCHEMES, COURSE_CODES)
    assert option_ids(result) == {"NSFDC_TL"}
    tl = result.options[0]
    assert tl.sanctionable_amount == 900000
    assert tl.own_contribution_required == 100000


def test_plantation_activity_extends_tl_moratorium_and_adds_reason():
    result = evaluate(
        business_profile(300000, is_plantation_or_construction=True), SCHEMES, COURSE_CODES
    )
    tl = next(o for o in result.options if o.option_id == "NSFDC_TL")
    assert tl.moratorium_months == 12
    assert any(r.code == "PLANTATION_EXTENDED_MORATORIUM" for r in tl.reasons)


def test_non_plantation_activity_keeps_standard_tl_moratorium():
    result = evaluate(business_profile(300000, is_plantation_or_construction=False), SCHEMES, COURSE_CODES)
    tl = next(o for o in result.options if o.option_id == "NSFDC_TL")
    assert tl.moratorium_months == 6
    assert not any(r.code == "PLANTATION_EXTENDED_MORATORIUM" for r in tl.reasons)


# --- education -------------------------------------------------------------------

def test_education_eligible_recognised_course_and_admission_confirmed():
    result = evaluate(education_profile(800000, remaining_months=48), SCHEMES, COURSE_CODES)
    assert result.eligible is True
    assert option_ids(result) == {"NSFDC_ELS"}
    els = result.options[0]
    assert els.sanctionable_amount == 720000
    assert els.own_contribution_required == 80000
    assert els.moratorium_months == 60  # 48 + 12


def test_education_blocked_when_admission_not_confirmed():
    result = evaluate(education_profile(800000, admission_confirmed=False), SCHEMES, COURSE_CODES)
    assert result.eligible is False
    assert result.blockers[0].code == "NO_ADMISSION_CONFIRMED"


def test_education_blocked_when_course_not_recognised():
    result = evaluate(education_profile(800000, course_code="ASTROLOGY_DIPLOMA"), SCHEMES, COURSE_CODES)
    assert result.eligible is False
    assert result.blockers[0].code == "COURSE_NOT_RECOGNISED"
    assert result.blockers[0].params["course_code"] == "ASTROLOGY_DIPLOMA"


def test_education_loan_capped_at_40_lakh_for_a_very_large_fee():
    result = evaluate(education_profile(6000000), SCHEMES, COURSE_CODES)
    assert result.eligible is True
    els = result.options[0]
    assert els.sanctionable_amount == 4000000  # capped, not 90% of 6,000,000
    assert els.own_contribution_required == 6000000 - 4000000


# --- reason codes, never prose -------------------------------------------------

def test_reasons_are_codes_with_params_not_prose():
    result = evaluate(business_profile(120000), SCHEMES, COURSE_CODES)
    for option in result.options:
        for reason in option.reasons:
            assert reason.code.isupper()
            assert isinstance(reason.params, dict)
            assert " " not in reason.code


# --- variant alternatives stay inert --------------------------------------------

def test_variant_alternatives_do_not_affect_default_evaluation():
    """els_variant/women_rebate_enabled/els_income_ceiling default to off;
    ELS eligibility must use the VERIFIED 500,000 ceiling and unified figures,
    never the VARIANT alternatives, unless explicitly switched (not implemented)."""
    assert SCHEMES.variants["els_variant"] == "unified_2026"
    assert SCHEMES.variants["women_rebate_enabled"] is False
    result = evaluate(education_profile(800000, income=400000), SCHEMES, COURSE_CODES)
    assert result.eligible is True
    # the 300,000 VARIANT ceiling must not apply
    blocked_under_variant_ceiling = evaluate(
        education_profile(800000, income=400000), SCHEMES, COURSE_CODES
    )
    assert blocked_under_variant_ceiling.eligible is True
