"""POST /recommend (BACKEND_BRIEF.md Step 5).

Orchestration only: parse the request, hand off to engine/eligibility.py and
engine/ranking.py for every decision, then shape their output into the
frozen API.md response. No eligibility, ranking or finance rule is
duplicated here.
"""
import uuid

from fastapi import APIRouter

from app.config import get_settings
from app.data_models import Scheme, SchemesFile
from app.engine import eligibility, ranking
from app.loader import LoadedData, get_data
from app.schemas import (
    CitationOut,
    ComparisonOut,
    DocumentOut,
    NextStepOut,
    OptionOut,
    ProfileIn,
    ReasonOut,
    RecommendRequest,
    RecommendResponse,
)

router = APIRouter()

NEXT_STEP_PORTAL = "https://pmsuraj.dosje.gov.in/"


def _new_request_id() -> str:
    return f"req_{uuid.uuid4().hex[:13]}"


def _scheme_by_id(schemes: SchemesFile, scheme_id: str) -> Scheme:
    return next(s for s in schemes.schemes if s.scheme_id == scheme_id)


def _build_profile(profile_in: ProfileIn, data: LoadedData) -> eligibility.Profile:
    is_plantation_or_construction = False
    if profile_in.purpose == "business" and profile_in.activity_code:
        activity = next(
            (a for a in data.activities.activities if a.activity_code == profile_in.activity_code),
            None,
        )
        if activity is not None:
            is_plantation_or_construction = activity.is_plantation_or_construction

    members = tuple(
        eligibility.Member(is_sc=m.is_sc, annual_family_income=m.annual_family_income)
        for m in (profile_in.members or [])
    )

    education = None
    if profile_in.education is not None:
        education = eligibility.EducationProfile(
            course_code=profile_in.education.course_code,
            study_location=profile_in.education.study_location,
            total_course_fee=profile_in.education.total_course_fee,
            remaining_course_months=profile_in.education.remaining_course_months,
            admission_confirmed=profile_in.education.admission_confirmed,
        )

    return eligibility.Profile(
        is_sc=profile_in.is_sc,
        annual_family_income=profile_in.annual_family_income,
        purpose=profile_in.purpose,
        applicant_type=profile_in.applicant_type,
        members=members,
        project_cost=profile_in.project_cost,
        is_plantation_or_construction=is_plantation_or_construction,
        education=education,
    )


def _reason_outs(reasons: list[eligibility.Reason]) -> list[ReasonOut]:
    return [ReasonOut(code=r.code, params=r.params) for r in reasons]


def _citations_for_option(schemes: SchemesFile, ranked: ranking.RankedOption) -> list[CitationOut]:
    scheme = _scheme_by_id(schemes, ranked.scheme_id)
    citations = [
        CitationOut(field=c.field, value=c.value, source_url=c.source_url, as_of=c.as_of)
        for c in scheme.citations
    ]
    if ranked.channel_variant_key and scheme.channel_variants:
        variant = next(v for v in scheme.channel_variants if v.key == ranked.channel_variant_key)
        citations.extend(
            CitationOut(field=c.field, value=c.value, source_url=c.source_url, as_of=c.as_of)
            for c in variant.citations
        )
    return citations


def _caveats_for_option(moratorium_treatment: str) -> list[ReasonOut]:
    # Attached to every option per BACKEND_BRIEF.md Step 5.
    return [
        ReasonOut(code="SANCTION_AT_PARTNER_DISCRETION", params={}),
        ReasonOut(code="MORATORIUM_TREATMENT_ASSUMED", params={"treatment": moratorium_treatment}),
    ]


def _option_out(schemes: SchemesFile, ranked: ranking.RankedOption, moratorium_treatment: str) -> OptionOut:
    scheme = _scheme_by_id(schemes, ranked.scheme_id)
    return OptionOut(
        option_id=ranked.option_id,
        rank=ranked.rank,
        scheme_id=ranked.scheme_id,
        scheme_name_key=scheme.name_key,
        channel_variant_key=ranked.channel_variant_key,
        channel_types=ranked.channel_types,
        project_cost=ranked.project_cost,
        sanctionable_amount=ranked.sanctionable_amount,
        own_contribution_required=ranked.own_contribution_required,
        financing_pct=ranked.financing_pct,
        interest_rate=ranked.interest_rate,
        instalment_frequency=scheme.instalment_frequency,
        total_period_months=ranked.total_period_months,
        moratorium_months=ranked.moratorium_months,
        number_of_instalments=ranked.number_of_instalments,
        principal_at_repayment_start=ranked.principal_at_repayment_start,
        instalment=ranked.instalment,
        monthly_equivalent=ranked.monthly_equivalent,
        total_outgo=ranked.total_outgo,
        total_interest=ranked.total_interest,
        indicative=True,
        data_tier=scheme.data_tier,
        reasons=_reason_outs(ranked.reasons),
        caveats=_caveats_for_option(moratorium_treatment),
        citations=_citations_for_option(schemes, ranked),
    )


@router.post("/recommend", response_model=RecommendResponse)
def recommend(request: RecommendRequest) -> RecommendResponse:
    data = get_data()
    settings = get_settings()
    moratorium_treatment = settings.moratorium_treatment

    recognised_course_codes = frozenset(c.course_code for c in data.courses.courses)
    profile = _build_profile(request.profile, data)

    eligibility_result = eligibility.evaluate(profile, data.schemes, recognised_course_codes)

    request_id = _new_request_id()
    ruleset_version = data.schemes.ruleset_version

    if not eligibility_result.eligible:
        return RecommendResponse(
            request_id=request_id,
            ruleset_version=ruleset_version,
            eligible=False,
            blockers=_reason_outs(eligibility_result.blockers),
            options=[],
            comparison=None,
            remediation=_reason_outs(eligibility_result.remediation),
            documents_required=[],
            next_step=None,
        )

    ranking_result = ranking.rank_options(
        eligibility_result,
        moratorium_treatment=moratorium_treatment,
        partner_counts_by_scheme_id={},  # Step 6 (partner locator) not implemented yet
    )

    options_out = [_option_out(data.schemes, ranked, moratorium_treatment) for ranked in ranking_result.options]

    recommended = ranking_result.options[0]
    checklist = data.documents.checklists[recommended.scheme_id]
    documents_required = [DocumentOut(code=item.code, mandatory=item.mandatory) for item in checklist]

    comparison = ComparisonOut(
        cheapest_option_id=ranking_result.comparison.cheapest_option_id,
        costliest_option_id=ranking_result.comparison.costliest_option_id,
        extra_cost_if_worst_route=ranking_result.comparison.extra_cost_if_worst_route,
        message_key=ranking_result.comparison.message_key,
    )

    return RecommendResponse(
        request_id=request_id,
        ruleset_version=ruleset_version,
        eligible=True,
        blockers=[],
        options=options_out,
        comparison=comparison,
        remediation=[],
        documents_required=documents_required,
        next_step=NextStepOut(key="next_step.visit_partner", external_portal=NEXT_STEP_PORTAL),
    )
