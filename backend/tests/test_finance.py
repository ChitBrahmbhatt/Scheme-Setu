"""Golden-case regression tests for the finance engine (CLAUDE.md §4).

These must pass before any other engine module is written — everything
downstream (recommend, calculate) depends on this arithmetic being correct.
"""
from decimal import Decimal

import pytest

from app.engine.finance import compute, build_schedule

GOLDEN_CASES = [
    # id,  sanctioned, rate,  total_months, moratorium, incl_mor, n,  instalment, outgo,    interest
    ("G1", 108000, "6.5", 36, 3, True, 11, 10977, 120747, 12747),
    ("G2", 108000, "15.0", 36, 3, True, 11, 12619, 138809, 30809),
    ("G3", 900000, "8.0", 84, 6, True, 26, 46518, 1209468, 309468),
    ("G4", 360000, "13.0", 60, 3, True, 19, 26527, 504013, 144013),
    ("G5", 360000, "8.0", 84, 6, True, 26, 18607, 483782, 123782),
    ("G6", 720000, "6.5", 144, 60, False, 48, 28777, 1381296, 661296),
    ("G10", 270000, "8.0", 84, 12, True, 24, 15417, 370008, 100008),
]


@pytest.mark.parametrize(
    "case_id,sanctioned,rate,total_months,mor,incl,n,instalment,outgo,interest",
    GOLDEN_CASES,
    ids=[c[0] for c in GOLDEN_CASES],
)
def test_golden_case(case_id, sanctioned, rate, total_months, mor, incl, n, instalment, outgo, interest):
    result = compute(
        sanctioned=Decimal(sanctioned),
        annual_rate=Decimal(rate),
        total_period_months=total_months,
        moratorium_months=mor,
        tenure_includes_moratorium=incl,
    )
    assert result.number_of_instalments == n
    assert result.instalment == instalment
    assert result.total_outgo == outgo
    assert result.total_interest == interest
    # arithmetic invariant, asserted per CLAUDE.md and API.md
    assert result.instalment * result.number_of_instalments == result.total_outgo
    assert result.total_outgo - sanctioned == result.total_interest


def test_g1_principal_at_repayment_start():
    result = compute(
        sanctioned=Decimal(108000),
        annual_rate=Decimal("6.5"),
        total_period_months=36,
        moratorium_months=3,
        tenure_includes_moratorium=True,
    )
    assert result.principal_at_repayment_start == 109755


def test_g6_principal_at_repayment_start():
    result = compute(
        sanctioned=Decimal(720000),
        annual_rate=Decimal("6.5"),
        total_period_months=144,
        moratorium_months=60,
        tenure_includes_moratorium=False,
    )
    assert result.principal_at_repayment_start == 954000


def test_monthly_equivalent_is_instalment_over_three():
    result = compute(
        sanctioned=Decimal(108000),
        annual_rate=Decimal("6.5"),
        total_period_months=36,
        moratorium_months=3,
        tenure_includes_moratorium=True,
    )
    assert result.monthly_equivalent == round(result.instalment / 3)


def test_serve_treatment_does_not_capitalise():
    result = compute(
        sanctioned=Decimal(108000),
        annual_rate=Decimal("6.5"),
        total_period_months=36,
        moratorium_months=3,
        tenure_includes_moratorium=True,
        moratorium_treatment="serve",
    )
    assert result.principal_at_repayment_start == 108000


def test_schedule_closing_balance_is_exactly_zero():
    result = compute(
        sanctioned=Decimal(900000),
        annual_rate=Decimal("8.0"),
        total_period_months=84,
        moratorium_months=6,
        tenure_includes_moratorium=True,
    )
    schedule = build_schedule(
        principal=result.principal_at_repayment_start,
        annual_rate=Decimal("8.0"),
        instalment=result.instalment,
        n=result.number_of_instalments,
    )
    assert len(schedule) == result.number_of_instalments
    assert schedule[-1].balance == 0
    # every row's instalment matches except the final one may absorb rounding residue
    total_principal_component = sum(row.principal for row in schedule)
    assert total_principal_component == result.principal_at_repayment_start


def test_schedule_is_internally_consistent_and_headline_invariant_holds():
    """The schedule and the headline instalment×n=total_outgo figure are two
    separate, documented things (CLAUDE.md §4): the headline uses the regular
    rounded instalment uniformly, while the schedule's final row absorbs
    rounding residue so the closing balance is exactly zero. They are not
    required to sum to the same total."""
    result = compute(
        sanctioned=Decimal(360000),
        annual_rate=Decimal("13.0"),
        total_period_months=60,
        moratorium_months=3,
        tenure_includes_moratorium=True,
    )
    schedule = build_schedule(
        principal=result.principal_at_repayment_start,
        annual_rate=Decimal("13.0"),
        instalment=result.instalment,
        n=result.number_of_instalments,
    )

    # 1. correct number of instalments
    assert len(schedule) == result.number_of_instalments

    # 2 & 3. every row has a valid interest/principal/payment/balance
    #    relationship: instalment == interest + principal component
    balance = result.principal_at_repayment_start
    for row in schedule:
        assert row.interest >= 0
        assert row.principal >= 0
        assert row.instalment == row.interest + row.principal
        balance -= row.principal
        assert row.balance == balance

    # 4. final balance is exactly zero
    assert schedule[-1].balance == 0

    # 5. all but the final instalment match the regular rounded instalment;
    #    the final one may differ to absorb rounding residue
    for row in schedule[:-1]:
        assert row.instalment == result.instalment
    # (the final row is allowed, not required, to differ)

    # 6. the headline invariant is untouched by schedule rounding
    assert result.instalment * result.number_of_instalments == result.total_outgo
