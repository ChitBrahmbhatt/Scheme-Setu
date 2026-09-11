"""Eligibility and per-scheme applicability (CLAUDE.md §5, BACKEND_BRIEF.md Step 3).

Pure, no I/O. Reason codes only, never prose — the caller (a later API layer)
maps codes to i18n strings. Ranking (LOWEST_COST_OPTION / ELIGIBLE_BUT_COSTLIER),
caveats, citations and the document checklist are attached downstream, not here.
"""
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from app.data_models import Scheme, SchemesFile

Purpose = Literal["business", "education"]
ApplicantType = Literal["individual", "partnership", "cooperative_society"]


def _round(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


@dataclass(frozen=True)
class Member:
    is_sc: bool
    annual_family_income: int


@dataclass(frozen=True)
class EducationProfile:
    course_code: str
    study_location: str
    total_course_fee: int
    remaining_course_months: int
    admission_confirmed: bool


@dataclass(frozen=True)
class Profile:
    is_sc: bool
    annual_family_income: int
    purpose: Purpose
    applicant_type: ApplicantType = "individual"
    members: tuple[Member, ...] = ()
    project_cost: int | None = None
    is_plantation_or_construction: bool = False
    education: EducationProfile | None = None


@dataclass(frozen=True)
class Reason:
    code: str
    params: dict = field(default_factory=dict)


@dataclass(frozen=True)
class SchemeApplicability:
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
    reasons: list[Reason]


@dataclass(frozen=True)
class EligibilityResult:
    eligible: bool
    blockers: list[Reason]
    remediation: list[Reason]
    options: list[SchemeApplicability]


def _scheme(schemes: SchemesFile, scheme_id: str) -> Scheme:
    return next(s for s in schemes.schemes if s.scheme_id == scheme_id)


def _within_range(value: int, minimum: int, min_exclusive: bool, maximum: int) -> bool:
    lower_ok = value > minimum if min_exclusive else value >= minimum
    return lower_ok and value <= maximum


def _sanctionable(cost: int, financing_pct: int, loan_max: int) -> int:
    raw = Decimal(cost) * Decimal(financing_pct) / Decimal(100)
    return min(_round(raw), loan_max)


def _evaluate_blockers(
    profile: Profile, income_ceiling: int
) -> tuple[list[Reason], list[Reason]]:
    blockers: list[Reason] = []

    if not profile.is_sc:
        blockers.append(Reason("NOT_SC"))
    if profile.annual_family_income > income_ceiling:
        blockers.append(
            Reason(
                "INCOME_ABOVE_CEILING",
                {"provided": profile.annual_family_income, "ceiling": income_ceiling},
            )
        )

    if profile.applicant_type in ("partnership", "cooperative_society"):
        for index, member in enumerate(profile.members):
            if not member.is_sc:
                blockers.append(Reason("MEMBER_NOT_SC", {"member_index": index}))
            if member.annual_family_income > income_ceiling:
                blockers.append(
                    Reason(
                        "MEMBER_INCOME_ABOVE_CEILING",
                        {
                            "member_index": index,
                            "provided": member.annual_family_income,
                            "ceiling": income_ceiling,
                        },
                    )
                )

    if not blockers:
        return [], []

    remediation: list[Reason] = [Reason("CHECK_NBCFDC"), Reason("REAPPLY_IF_INCOME_CHANGES")]
    return blockers, remediation


def _business_options(
    profile: Profile, schemes: SchemesFile, income_ceiling: int
) -> tuple[list[SchemeApplicability], Reason | None]:
    cost = profile.project_cost
    options: list[SchemeApplicability] = []

    income_reason = Reason("INCOME_WITHIN_CEILING", {"ceiling": income_ceiling})

    for scheme_id in ("NSFDC_MFS", "NSFDC_AMY"):
        scheme = _scheme(schemes, scheme_id)
        if _within_range(cost, scheme.project_cost_min, False, scheme.project_cost_max):
            sanctionable = _sanctionable(cost, scheme.financing_pct, scheme.loan_max)
            options.append(
                SchemeApplicability(
                    option_id=scheme.scheme_id,
                    scheme_id=scheme.scheme_id,
                    channel_variant_key=None,
                    channel_types=list(scheme.channel_types),
                    interest_rate=scheme.interest_rate,
                    financing_pct=scheme.financing_pct,
                    total_period_months=scheme.total_period_months,
                    tenure_includes_moratorium=scheme.tenure_includes_moratorium,
                    moratorium_months=scheme.moratorium_months,
                    project_cost=cost,
                    sanctionable_amount=sanctionable,
                    own_contribution_required=cost - sanctionable,
                    reasons=[Reason("COST_WITHIN_MFS_CAP", {"cap": scheme.project_cost_max}), income_reason],
                )
            )

    uny = _scheme(schemes, "NSFDC_UNY")
    if _within_range(cost, uny.project_cost_min, False, uny.project_cost_max):
        sanctionable = _sanctionable(cost, uny.financing_pct, uny.loan_max)
        for variant in uny.channel_variants:
            options.append(
                SchemeApplicability(
                    option_id=f"NSFDC_UNY.{variant.variant_id}",
                    scheme_id="NSFDC_UNY",
                    channel_variant_key=variant.key,
                    channel_types=list(variant.channel_types),
                    interest_rate=variant.interest_rate,
                    financing_pct=uny.financing_pct,
                    total_period_months=uny.total_period_months,
                    tenure_includes_moratorium=uny.tenure_includes_moratorium,
                    moratorium_months=uny.moratorium_months,
                    project_cost=cost,
                    sanctionable_amount=sanctionable,
                    own_contribution_required=cost - sanctionable,
                    reasons=[Reason("COST_WITHIN_UNY_CAP", {"cap": uny.project_cost_max}), income_reason],
                )
            )

    tl = _scheme(schemes, "NSFDC_TL")
    tl_min_exclusive = getattr(tl, "project_cost_min_exclusive", False)
    tl_loan_min_exclusive = getattr(tl, "loan_min_exclusive", False)
    if _within_range(cost, tl.project_cost_min, tl_min_exclusive, tl.project_cost_max):
        sanctionable = _sanctionable(cost, tl.financing_pct, tl.loan_max)
        loan_min_ok = sanctionable > tl.loan_min if tl_loan_min_exclusive else sanctionable >= tl.loan_min
        if loan_min_ok:
            moratorium_months = (
                tl.moratorium_months_special
                if profile.is_plantation_or_construction and tl.moratorium_months_special
                else tl.moratorium_months
            )
            reasons = [Reason("COST_REQUIRES_TERM_LOAN", {"cap": tl.project_cost_min}), income_reason]
            if profile.is_plantation_or_construction:
                reasons.append(Reason("PLANTATION_EXTENDED_MORATORIUM"))
            options.append(
                SchemeApplicability(
                    option_id=tl.scheme_id,
                    scheme_id=tl.scheme_id,
                    channel_variant_key=None,
                    channel_types=list(tl.channel_types),
                    interest_rate=tl.interest_rate,
                    financing_pct=tl.financing_pct,
                    total_period_months=tl.total_period_months,
                    tenure_includes_moratorium=tl.tenure_includes_moratorium,
                    moratorium_months=moratorium_months,
                    project_cost=cost,
                    sanctionable_amount=sanctionable,
                    own_contribution_required=cost - sanctionable,
                    reasons=reasons,
                )
            )

    if not options:
        return [], Reason("COST_ABOVE_ALL_CAPS", {"project_cost": cost})

    return options, None


def _education_options(
    profile: Profile,
    schemes: SchemesFile,
    income_ceiling: int,
    recognised_course_codes: frozenset[str],
) -> tuple[list[SchemeApplicability], Reason | None]:
    edu = profile.education
    els = _scheme(schemes, "NSFDC_ELS")

    if not edu.admission_confirmed:
        return [], Reason("NO_ADMISSION_CONFIRMED")
    if edu.course_code not in recognised_course_codes:
        return [], Reason("COURSE_NOT_RECOGNISED", {"course_code": edu.course_code})

    sanctionable = _sanctionable(edu.total_course_fee, els.financing_pct, els.loan_max)
    moratorium_months = edu.remaining_course_months + 12

    option = SchemeApplicability(
        option_id=els.scheme_id,
        scheme_id=els.scheme_id,
        channel_variant_key=None,
        channel_types=list(els.channel_types),
        interest_rate=els.interest_rate,
        financing_pct=els.financing_pct,
        total_period_months=els.total_period_months,
        tenure_includes_moratorium=els.tenure_includes_moratorium,
        moratorium_months=moratorium_months,
        project_cost=edu.total_course_fee,
        sanctionable_amount=sanctionable,
        own_contribution_required=edu.total_course_fee - sanctionable,
        reasons=[Reason("INCOME_WITHIN_CEILING", {"ceiling": income_ceiling})],
    )
    return [option], None


def evaluate(
    profile: Profile,
    schemes: SchemesFile,
    recognised_course_codes: frozenset[str] = frozenset(),
) -> EligibilityResult:
    income_ceiling = schemes.eligibility["income_ceiling"]

    blockers, remediation = _evaluate_blockers(profile, income_ceiling)
    if blockers:
        return EligibilityResult(eligible=False, blockers=blockers, remediation=remediation, options=[])

    if profile.purpose == "business":
        options, no_fit_reason = _business_options(profile, schemes, income_ceiling)
    else:
        options, no_fit_reason = _education_options(profile, schemes, income_ceiling, recognised_course_codes)

    if no_fit_reason is not None:
        return EligibilityResult(eligible=False, blockers=[no_fit_reason], remediation=[], options=[])

    return EligibilityResult(eligible=True, blockers=[], remediation=[], options=options)
