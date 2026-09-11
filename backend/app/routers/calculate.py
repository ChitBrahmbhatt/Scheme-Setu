"""POST /calculate (BACKEND_BRIEF.md Step 5).

Standalone what-if control. Validates the request against the loaded scheme
config, then delegates all arithmetic to engine/finance.py — no formula is
duplicated here.
"""
from decimal import Decimal

from fastapi import APIRouter

from app.config import get_settings
from app.data_models import Scheme
from app.engine import finance
from app.errors import ApiError
from app.loader import get_data
from app.schemas import CalculateRequest, CalculateResponse, ScheduleRowOut

router = APIRouter()


def _find_scheme(scheme_id: str) -> Scheme:
    data = get_data()
    scheme = next((s for s in data.schemes.schemes if s.scheme_id == scheme_id), None)
    if scheme is None:
        raise ApiError("NOT_FOUND", f"Unknown scheme_id '{scheme_id}'.", field="scheme_id", status_code=404)
    return scheme


def _resolve_rate(scheme: Scheme, channel_variant: str | None) -> float:
    if scheme.channel_variants:
        if channel_variant is None:
            raise ApiError(
                "VALIDATION_ERROR",
                f"channel_variant is required for scheme '{scheme.scheme_id}'.",
                field="channel_variant",
            )
        variant = next((v for v in scheme.channel_variants if v.variant_id == channel_variant), None)
        if variant is None:
            valid = ", ".join(v.variant_id for v in scheme.channel_variants)
            raise ApiError(
                "VALIDATION_ERROR",
                f"channel_variant must be one of [{valid}] for scheme '{scheme.scheme_id}'.",
                field="channel_variant",
            )
        return variant.interest_rate

    if channel_variant is not None:
        raise ApiError(
            "VALIDATION_ERROR",
            f"scheme '{scheme.scheme_id}' does not accept a channel_variant.",
            field="channel_variant",
        )
    return scheme.interest_rate


def _validate_caps(scheme: Scheme, request: CalculateRequest) -> None:
    if request.sanctioned_amount > scheme.loan_max:
        raise ApiError(
            "VALIDATION_ERROR",
            f"sanctioned_amount must not exceed ₹{scheme.loan_max} for scheme '{scheme.scheme_id}'.",
            field="sanctioned_amount",
        )

    if request.total_period_months > scheme.total_period_months:
        raise ApiError(
            "VALIDATION_ERROR",
            f"total_period_months must not exceed {scheme.total_period_months} for scheme '{scheme.scheme_id}'.",
            field="total_period_months",
        )

    # Schemes with no static moratorium field (NSFDC_ELS: derived dynamically
    # from course length as remaining_course_months + 12) have no fixed cap
    # to validate a standalone /calculate call against.
    static_caps = [m for m in (scheme.moratorium_months, scheme.moratorium_months_special) if m is not None]
    if static_caps:
        moratorium_cap = max(static_caps)
        if request.moratorium_months > moratorium_cap:
            raise ApiError(
                "VALIDATION_ERROR",
                f"moratorium_months must not exceed {moratorium_cap} for scheme '{scheme.scheme_id}'.",
                field="moratorium_months",
            )

    repayment_months = (
        request.total_period_months - request.moratorium_months
        if scheme.tenure_includes_moratorium
        else request.total_period_months
    )
    if repayment_months < 3:
        raise ApiError(
            "VALIDATION_ERROR",
            "The repayment period must allow at least one quarterly instalment.",
            field="moratorium_months",
        )


@router.post("/calculate", response_model=CalculateResponse)
def calculate(request: CalculateRequest) -> CalculateResponse:
    scheme = _find_scheme(request.scheme_id)
    interest_rate = _resolve_rate(scheme, request.channel_variant)
    _validate_caps(scheme, request)

    settings = get_settings()
    moratorium_treatment = settings.moratorium_treatment

    result = finance.compute(
        sanctioned=Decimal(request.sanctioned_amount),
        annual_rate=Decimal(str(interest_rate)),
        total_period_months=request.total_period_months,
        moratorium_months=request.moratorium_months,
        tenure_includes_moratorium=scheme.tenure_includes_moratorium,
        moratorium_treatment=moratorium_treatment,
    )

    schedule_out = None
    if request.include_schedule:
        schedule = finance.build_schedule(
            principal=result.principal_at_repayment_start,
            annual_rate=Decimal(str(interest_rate)),
            instalment=result.instalment,
            n=result.number_of_instalments,
        )
        schedule_out = [
            ScheduleRowOut(
                n=row.n,
                due_month=request.moratorium_months + 3 * row.n,
                instalment=row.instalment,
                interest=row.interest,
                principal=row.principal,
                balance=row.balance,
            )
            for row in schedule
        ]

    return CalculateResponse(
        scheme_id=scheme.scheme_id,
        interest_rate=interest_rate,
        instalment_frequency=scheme.instalment_frequency,
        sanctioned_amount=request.sanctioned_amount,
        moratorium_months=request.moratorium_months,
        moratorium_treatment=moratorium_treatment,
        principal_at_repayment_start=result.principal_at_repayment_start,
        number_of_instalments=result.number_of_instalments,
        instalment=result.instalment,
        monthly_equivalent=result.monthly_equivalent,
        total_outgo=result.total_outgo,
        total_interest=result.total_interest,
        indicative=True,
        data_tier=scheme.data_tier,
        schedule=schedule_out,
    )
