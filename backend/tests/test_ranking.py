"""Ranking engine tests (CLAUDE.md §5, BACKEND_BRIEF.md Step 4)."""
from pathlib import Path

from app.engine.eligibility import EligibilityResult, Profile, Reason, SchemeApplicability, evaluate
from app.engine.ranking import rank_options
from app.loader import load_all

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
DATA = load_all(DATA_DIR)
SCHEMES = DATA.schemes
COURSE_CODES = frozenset(c.course_code for c in DATA.courses.courses)


def business_profile(project_cost, income=240000, **kwargs):
    return Profile(is_sc=True, annual_family_income=income, purpose="business",
                    project_cost=project_cost, **kwargs)


def option(
    option_id,
    scheme_id,
    total_interest_inputs,  # (sanctioned, rate, total_period_months, moratorium_months, tenure_includes_moratorium)
    channel_variant_key=None,
    channel_types=None,
):
    sanctioned, rate, total_period_months, moratorium_months, tenure_includes = total_interest_inputs
    return SchemeApplicability(
        option_id=option_id,
        scheme_id=scheme_id,
        channel_variant_key=channel_variant_key,
        channel_types=channel_types or ["SCA"],
        interest_rate=rate,
        financing_pct=90,
        total_period_months=total_period_months,
        tenure_includes_moratorium=tenure_includes,
        moratorium_months=moratorium_months,
        project_cost=sanctioned,
        sanctionable_amount=sanctioned,
        own_contribution_required=0,
        reasons=[Reason("COST_WITHIN_MFS_CAP", {"cap": 140000})],
    )


def eligibility_of(options):
    return EligibilityResult(eligible=True, blockers=[], remediation=[], options=options)


def option_ids(ranking_result):
    return [o.option_id for o in ranking_result.options]


# --- MFS vs AMY (real eligibility path) ----------------------------------------

def test_mfs_ranks_first_over_amy_at_120000():
    eligibility_result = evaluate(business_profile(120000), SCHEMES, COURSE_CODES)
    result = rank_options(eligibility_result)
    assert result.options[0].option_id == "NSFDC_MFS"
    assert result.options[0].total_interest == 12747
    assert result.recommended_option_id == "NSFDC_MFS"


def test_mfs_vs_amy_comparison_preserves_both_eligible_options():
    """CLAUDE.md's literal per-scheme rule also makes UNY (both variants)
    eligible at ₹1,20,000 (project_cost <= 500,000) alongside MFS/AMY —
    confirmed authoritative over API.md's abbreviated 2-option example.
    All four eligible options must survive ranking, never truncated."""
    eligibility_result = evaluate(business_profile(120000), SCHEMES, COURSE_CODES)
    result = rank_options(eligibility_result)
    ids = set(option_ids(result))
    assert {"NSFDC_MFS", "NSFDC_AMY"} <= ids
    assert len(result.options) == len(eligibility_result.options)
    amy = next(o for o in result.options if o.option_id == "NSFDC_AMY")
    assert amy.total_interest == 30809
    assert any(r.code == "ELIGIBLE_BUT_COSTLIER" for r in amy.reasons)


# --- UNY vs Term Loan (G4/G5 dairy) --------------------------------------------

def test_uny_vs_term_loan_dairy_project_ranking():
    eligibility_result = evaluate(business_profile(400000), SCHEMES, COURSE_CODES)
    result = rank_options(eligibility_result)
    assert option_ids(result) == ["NSFDC_TL", "NSFDC_UNY.COOP", "NSFDC_UNY.SFB"]
    tl, coop, sfb = result.options
    assert tl.total_interest == 123782
    assert coop.total_interest == 144013  # corrected G4 figure
    assert sfb.total_interest == 168903
    assert result.recommended_option_id == "NSFDC_TL"
    assert result.comparison.extra_cost_if_worst_route == 168903 - 123782


# --- ordering is by computed interest, not config/input order ------------------

def test_interest_based_ranking_beats_input_order():
    options = [
        option("HIGH", "SCHEME_HIGH", (100000, 20.0, 36, 3, True)),
        option("LOW", "SCHEME_LOW", (100000, 6.0, 36, 3, True)),
    ]
    result = rank_options(eligibility_of(options))
    assert option_ids(result) == ["LOW", "HIGH"]
    assert result.options[0].total_interest < result.options[1].total_interest


# --- tie-breakers ---------------------------------------------------------------

def test_tie_on_interest_shorter_repayment_period_wins():
    # same sanctioned/rate, same n=11 via different total_period_months/moratorium.
    # Use "serve" treatment so principal_at_repayment_start (and therefore
    # total_interest) depends only on sanctioned/rate/n, not on moratorium_months,
    # letting total_period_months vary independently while interest genuinely ties.
    shorter = option("SHORT", "SCHEME_SHORT", (100000, 10.0, 36, 3, True))   # n=11
    longer = option("LONG", "SCHEME_LONG", (100000, 10.0, 48, 15, True))     # n=11
    assert shorter.total_period_months < longer.total_period_months

    result = rank_options(eligibility_of([longer, shorter]), moratorium_treatment="serve")
    # sanity: both actually tie on total_interest before asserting the tiebreak
    assert result.options[0].total_interest == result.options[1].total_interest
    assert option_ids(result) == ["SHORT", "LONG"]


def test_tie_on_interest_and_period_more_district_partners_wins():
    a = option("A", "SCHEME_A", (100000, 10.0, 36, 3, True))
    b = option("B", "SCHEME_B", (100000, 10.0, 36, 3, True))
    result = rank_options(
        eligibility_of([a, b]),
        partner_counts_by_scheme_id={"SCHEME_A": 2, "SCHEME_B": 5},
    )
    assert result.options[0].total_interest == result.options[1].total_interest
    assert result.options[0].total_period_months == result.options[1].total_period_months
    assert option_ids(result) == ["B", "A"]


def test_deterministic_ordering_when_all_ranking_fields_tie():
    a = option("A", "SCHEME_A", (100000, 10.0, 36, 3, True))
    b = option("B", "SCHEME_B", (100000, 10.0, 36, 3, True))
    result_ab = rank_options(eligibility_of([a, b]))
    result_ba = rank_options(eligibility_of([b, a]))
    # stable sort: no partner counts given (both 0), so original input order
    # is preserved deterministically rather than an invented id-based tiebreak
    assert option_ids(result_ab) == ["A", "B"]
    assert option_ids(result_ba) == ["B", "A"]


# --- blocked / ineligible profiles --------------------------------------------

def test_only_eligible_schemes_enter_ranking_cost_above_all_caps():
    eligibility_result = evaluate(business_profile(6000000), SCHEMES, COURSE_CODES)
    assert eligibility_result.eligible is False
    result = rank_options(eligibility_result)
    assert result.options == []
    assert result.comparison is None
    assert result.recommended_option_id is None


def test_no_ranking_for_hard_blocked_profile():
    eligibility_result = evaluate(
        Profile(is_sc=False, annual_family_income=240000, purpose="business", project_cost=120000),
        SCHEMES, COURSE_CODES,
    )
    assert eligibility_result.blockers[0].code == "NOT_SC"
    result = rank_options(eligibility_result)
    assert result.options == []
    assert result.comparison is None
    assert result.recommended_option_id is None


# --- education options ----------------------------------------------------------

def test_education_option_ranks_with_finance_derived_figures():
    from app.engine.eligibility import EducationProfile

    profile = Profile(
        is_sc=True, annual_family_income=240000, purpose="education",
        education=EducationProfile(
            course_code="BTECH", study_location="india", total_course_fee=800000,
            remaining_course_months=48, admission_confirmed=True,
        ),
    )
    eligibility_result = evaluate(profile, SCHEMES, COURSE_CODES)
    result = rank_options(eligibility_result)
    assert len(result.options) == 1
    els = result.options[0]
    assert els.option_id == "NSFDC_ELS"
    assert els.number_of_instalments == 48
    assert els.instalment == 28777
    assert els.total_outgo == 1381296
    assert els.total_interest == 661296
    assert result.recommended_option_id == "NSFDC_ELS"
    assert any(r.code == "LOWEST_COST_OPTION" for r in els.reasons)


# --- VARIANT alternatives stay inert --------------------------------------------

def test_variant_alternatives_do_not_leak_into_ranked_options():
    eligibility_result = evaluate(business_profile(120000), SCHEMES, COURSE_CODES)
    result = rank_options(eligibility_result)
    ids = option_ids(result)
    assert "NSFDC_ELS.split_legacy" not in ids
    assert not any("split_legacy" in oid or "women_rebate" in oid for oid in ids)
    assert SCHEMES.variants["els_variant"] == "unified_2026"


# --- recommended option / no mutation -------------------------------------------

def test_recommended_option_is_always_the_first_ranked_option():
    eligibility_result = evaluate(business_profile(400000), SCHEMES, COURSE_CODES)
    result = rank_options(eligibility_result)
    assert result.recommended_option_id == result.options[0].option_id


def test_ranking_does_not_mutate_eligibility_result():
    eligibility_result = evaluate(business_profile(120000), SCHEMES, COURSE_CODES)
    original_ids = [o.option_id for o in eligibility_result.options]
    original_reasons = [list(o.reasons) for o in eligibility_result.options]

    rank_options(eligibility_result)

    assert [o.option_id for o in eligibility_result.options] == original_ids
    assert [list(o.reasons) for o in eligibility_result.options] == original_reasons
