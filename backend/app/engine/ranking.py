"""Ranking and the cost-of-route comparison (CLAUDE.md §5, BACKEND_BRIEF.md Step 4).

Pure, no I/O, no network. Consumes an already-computed EligibilityResult from
engine/eligibility.py without recomputing or overriding its eligibility
decision — this module only prices and orders the options eligibility already
decided were applicable.

Ranking: ascending total_interest. Ties -> shorter total_period_months, then
more partners available in the user's district. Python's sorted() is stable,
so if every ranking field ties, input order (from eligibility.py) is
preserved deterministically without inventing an undocumented tiebreaker.
"""
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal

from app.engine import finance
from app.engine.eligibility import EligibilityResult, Reason, SchemeApplicability


@dataclass(frozen=True)
class RankedOption:
    option_id: str
    scheme_id: str
    channel_variant_key: str | None
    channel_types: list[str]
    interest_rate: float
    financing_pct: int
    total_period_months: int
    tenure_includes_moratorium: bool
    moratorium_months: int
    project_cost: int
    sanctionable_amount: int
    own_contribution_required: int
    number_of_instalments: int
    principal_at_repayment_start: int
    instalment: int
    monthly_equivalent: int
    total_outgo: int
    total_interest: int
    rank: int
    reasons: list[Reason] = field(default_factory=list)


@dataclass(frozen=True)
class Comparison:
    cheapest_option_id: str
    costliest_option_id: str
    extra_cost_if_worst_route: int
    message_key: str = "comparison.route_matters"


@dataclass(frozen=True)
class RankingResult:
    options: list[RankedOption]
    comparison: Comparison | None
    recommended_option_id: str | None


def _price(option: SchemeApplicability, moratorium_treatment: str) -> finance.InstalmentResult:
    return finance.compute(
        sanctioned=Decimal(option.sanctionable_amount),
        annual_rate=Decimal(str(option.interest_rate)),
        total_period_months=option.total_period_months,
        moratorium_months=option.moratorium_months,
        tenure_includes_moratorium=option.tenure_includes_moratorium,
        moratorium_treatment=moratorium_treatment,
    )


def rank_options(
    eligibility_result: EligibilityResult,
    moratorium_treatment: str = "capitalise",
    partner_counts_by_scheme_id: Mapping[str, int] | None = None,
) -> RankingResult:
    """Price and rank the options eligibility.py already decided are
    applicable. Never re-evaluates eligibility; an ineligible or blocked
    result (empty options) simply yields an empty ranking."""
    if not eligibility_result.eligible or not eligibility_result.options:
        return RankingResult(options=[], comparison=None, recommended_option_id=None)

    partner_counts = partner_counts_by_scheme_id or {}

    priced = [
        (option, _price(option, moratorium_treatment))
        for option in eligibility_result.options
    ]

    def sort_key(item: tuple[SchemeApplicability, finance.InstalmentResult]):
        option, priced_result = item
        partner_count = partner_counts.get(option.scheme_id, 0)
        return (priced_result.total_interest, option.total_period_months, -partner_count)

    ordered = sorted(priced, key=sort_key)
    cheapest_interest = ordered[0][1].total_interest

    ranked_options: list[RankedOption] = []
    for index, (option, priced_result) in enumerate(ordered, start=1):
        if index == 1:
            reasons = list(option.reasons) + [Reason("LOWEST_COST_OPTION")]
        else:
            delta = priced_result.total_interest - cheapest_interest
            reasons = [Reason("ELIGIBLE_BUT_COSTLIER", {"delta": delta})]

        ranked_options.append(
            RankedOption(
                option_id=option.option_id,
                scheme_id=option.scheme_id,
                channel_variant_key=option.channel_variant_key,
                channel_types=option.channel_types,
                interest_rate=option.interest_rate,
                financing_pct=option.financing_pct,
                total_period_months=option.total_period_months,
                tenure_includes_moratorium=option.tenure_includes_moratorium,
                moratorium_months=option.moratorium_months,
                project_cost=option.project_cost,
                sanctionable_amount=option.sanctionable_amount,
                own_contribution_required=option.own_contribution_required,
                number_of_instalments=priced_result.number_of_instalments,
                principal_at_repayment_start=priced_result.principal_at_repayment_start,
                instalment=priced_result.instalment,
                monthly_equivalent=priced_result.monthly_equivalent,
                total_outgo=priced_result.total_outgo,
                total_interest=priced_result.total_interest,
                rank=index,
                reasons=reasons,
            )
        )

    cheapest = ranked_options[0]
    costliest = ranked_options[-1]
    comparison = Comparison(
        cheapest_option_id=cheapest.option_id,
        costliest_option_id=costliest.option_id,
        extra_cost_if_worst_route=costliest.total_interest - cheapest.total_interest,
    )

    return RankingResult(
        options=ranked_options,
        comparison=comparison,
        recommended_option_id=cheapest.option_id,
    )
