"""Request/response models for the frozen contract (API.md).

Pydantic validates at the boundary (BACKEND_BRIEF.md §3); the shapes here
must match API.md exactly — this file does not redesign the contract.
"""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Locale = Literal["en", "hi"]
ApplicantType = Literal["individual", "partnership", "cooperative_society"]
Purpose = Literal["business", "education"]
StudyLocation = Literal["india", "abroad"]


# --- /recommend request --------------------------------------------------------

class MemberIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_sc: bool
    annual_family_income: int = Field(ge=0, le=100_000_000)


class EducationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    course_code: str
    study_location: StudyLocation = "india"
    total_course_fee: int = Field(gt=0, le=50_000_000)
    remaining_course_months: int = Field(ge=0, le=240)
    admission_confirmed: bool


class ProfileIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    applicant_type: ApplicantType = "individual"
    is_sc: bool
    annual_family_income: int = Field(ge=0, le=100_000_000)
    gender: str | None = None
    purpose: Purpose
    activity_code: str | None = None
    project_cost: int | None = Field(default=None, gt=0, le=50_000_000)
    education: EducationIn | None = None
    members: list[MemberIn] | None = None
    state_code: str | None = None
    district: str | None = None
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)

    @model_validator(mode="after")
    def _purpose_matches_payload(self):
        if self.purpose == "business":
            if self.education is not None:
                raise ValueError("education must not be supplied when purpose is business")
            if not self.activity_code or self.project_cost is None:
                raise ValueError("activity_code and project_cost are required when purpose is business")
        else:
            if self.activity_code is not None or self.project_cost is not None:
                raise ValueError("activity_code/project_cost must not be supplied when purpose is education")
            if self.education is None:
                raise ValueError("education is required when purpose is education")

        if self.applicant_type in ("partnership", "cooperative_society") and not self.members:
            raise ValueError("members is required when applicant_type is partnership or cooperative_society")
        return self


class RecommendRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    locale: Locale = "en"
    profile: ProfileIn


# --- /recommend response --------------------------------------------------------

class ReasonOut(BaseModel):
    code: str
    params: dict = Field(default_factory=dict)


class CitationOut(BaseModel):
    field: str
    value: str
    source_url: str
    as_of: str


class OptionOut(BaseModel):
    option_id: str
    rank: int
    scheme_id: str
    scheme_name_key: str
    channel_variant_key: str | None
    channel_types: list[str]

    project_cost: int
    sanctionable_amount: int
    own_contribution_required: int
    financing_pct: int

    interest_rate: float
    instalment_frequency: str
    total_period_months: int
    moratorium_months: int
    number_of_instalments: int
    principal_at_repayment_start: int

    instalment: int
    monthly_equivalent: int
    total_outgo: int
    total_interest: int

    indicative: bool
    data_tier: str
    reasons: list[ReasonOut]
    caveats: list[ReasonOut]
    citations: list[CitationOut]


class ComparisonOut(BaseModel):
    cheapest_option_id: str
    costliest_option_id: str
    extra_cost_if_worst_route: int
    message_key: str = "comparison.route_matters"


class DocumentOut(BaseModel):
    code: str
    mandatory: bool


class NextStepOut(BaseModel):
    key: str
    external_portal: str


class RecommendResponse(BaseModel):
    request_id: str
    ruleset_version: str
    eligible: bool
    blockers: list[ReasonOut]
    options: list[OptionOut]
    comparison: ComparisonOut | None
    remediation: list[ReasonOut] = Field(default_factory=list)
    documents_required: list[DocumentOut]
    next_step: NextStepOut | None


# --- /calculate request/response -------------------------------------------------

class CalculateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scheme_id: str
    channel_variant: str | None = None
    sanctioned_amount: int = Field(gt=0, le=50_000_000)
    total_period_months: int = Field(gt=0, le=600)
    moratorium_months: int = Field(ge=0, le=600)
    include_schedule: bool = False


class ScheduleRowOut(BaseModel):
    n: int
    due_month: int
    instalment: int
    interest: int
    principal: int
    balance: int


class CalculateResponse(BaseModel):
    scheme_id: str
    interest_rate: float
    instalment_frequency: str
    sanctioned_amount: int
    moratorium_months: int
    moratorium_treatment: str
    principal_at_repayment_start: int
    number_of_instalments: int
    instalment: int
    monthly_equivalent: int
    total_outgo: int
    total_interest: int
    indicative: bool
    data_tier: str
    schedule: list[ScheduleRowOut] | None = None


# --- GET /partners response (API.md §3) -----------------------------------------

class PartnerIndicatorsOut(BaseModel):
    fund_utilisation_pct: float
    overdue_ratio_pct: float
    avg_sanction_days: int


class PartnerOut(BaseModel):
    partner_id: str
    name: str
    branch_label: str
    type: str
    address: str
    district: str
    state: str
    state_code: str
    pincode: str
    lat: float
    lng: float
    phone: str
    distance_km: float | None
    schemes_supported: list[str]
    routing_status: str
    routing_reasons: list[ReasonOut]
    indicators: PartnerIndicatorsOut
    data_tier: str


class ExcludedPartnerOut(BaseModel):
    partner_id: str
    name: str
    branch_label: str
    distance_km: float | None
    type: str
    routing_status: str
    routing_reasons: list[ReasonOut]
    data_tier: str


class ExcludedBlockOut(BaseModel):
    count: int
    items: list[ExcludedPartnerOut]


class PartnersQueryOut(BaseModel):
    scheme_id: str
    lat: float | None = None
    lng: float | None = None
    state_code: str | None = None
    district: str | None = None
    radius_km: float | None = None
    limit: int | None = None


class PartnersResponse(BaseModel):
    request_id: str
    ruleset_version: str
    query: PartnersQueryOut
    data_tier: str = "SIMULATED"
    disclaimer_key: str = "partners.dataset_simulated"
    partners: list[PartnerOut]
    excluded: ExcludedBlockOut


# --- reference-data endpoints (API.md §4) ---------------------------------------

class ActivityOut(BaseModel):
    activity_code: str
    name_key: str
    indicative_cost_min: int
    indicative_cost_max: int
    is_plantation_or_construction: bool


class ActivitiesResponse(BaseModel):
    activities: list[ActivityOut]


class CourseOut(BaseModel):
    course_code: str
    name_key: str
    level: str
    typical_duration_months: int


class CoursesResponse(BaseModel):
    courses: list[CourseOut]


class DocumentsRequiredResponse(BaseModel):
    documents_required: list[DocumentOut]
