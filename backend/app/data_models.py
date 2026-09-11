"""Pydantic models for the JSON data files (BACKEND_BRIEF.md Step 2).

Validated once at startup by loader.py so a malformed data file fails loudly
at boot rather than surfacing as a confusing error on the first request.
"""
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

DataTier = Literal["VERIFIED", "VARIANT", "SIMULATED"]


class Citation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str
    value: str
    source_url: str
    as_of: str


class ChannelVariant(BaseModel):
    model_config = ConfigDict(extra="forbid")

    variant_id: str
    key: str
    interest_rate: float
    channel_types: list[str]
    citations: list[Citation] = []


class Scheme(BaseModel):
    model_config = ConfigDict(extra="allow")

    scheme_id: str
    name_key: str
    purpose: Literal["business", "education"]
    project_cost_min: int
    project_cost_max: int
    financing_pct: int
    loan_min: int
    loan_max: int
    interest_rate: float | None
    channel_variants: list[ChannelVariant] | None
    channel_types: list[str] | None
    total_period_months: int
    tenure_includes_moratorium: bool
    moratorium_months: int | None
    moratorium_months_special: int | None
    instalment_frequency: str
    data_tier: DataTier
    citations: list[Citation]

    @model_validator(mode="after")
    def _rate_or_variants(self):
        has_rate = self.interest_rate is not None
        has_variants = bool(self.channel_variants)
        if has_rate == has_variants:
            raise ValueError(
                f"{self.scheme_id}: exactly one of interest_rate or channel_variants must be set"
            )
        return self


class SchemeAssumption(BaseModel):
    model_config = ConfigDict(extra="allow")

    code: str
    applies_to: str
    note: str
    label_as: Literal["assumption"]


class SchemesFile(BaseModel):
    model_config = ConfigDict(extra="allow")

    ruleset_version: str
    moratorium_treatment: Literal["capitalise", "serve", "defer"]
    variants: dict
    eligibility: dict
    assumptions: list[SchemeAssumption]
    schemes: list[Scheme]

    @model_validator(mode="after")
    def _five_schemes_required_ids(self):
        expected = {"NSFDC_MFS", "NSFDC_TL", "NSFDC_AMY", "NSFDC_UNY", "NSFDC_ELS"}
        found = {s.scheme_id for s in self.schemes}
        if found != expected:
            raise ValueError(f"schemes.json must define exactly {expected}, found {found}")
        return self


class Partner(BaseModel):
    model_config = ConfigDict(extra="forbid")

    partner_id: str
    name: str
    branch_label: str
    type: Literal["SCA", "PSB", "RRB", "NBFC_MFI", "COOP_BANK", "COOP_SOCIETY", "SFB"]
    address: str
    district: str
    state: str
    state_code: str
    pincode: str
    lat: float
    lng: float
    phone: str
    schemes_supported: list[str]
    fund_utilisation_pct: float
    overdue_ratio_pct: float
    avg_sanction_days: int
    data_tier: Literal["SIMULATED"]


class PartnersFile(BaseModel):
    model_config = ConfigDict(extra="allow")

    ruleset_version: str
    data_tier: Literal["SIMULATED"]
    disclaimer_key: str
    partners: list[Partner]

    @model_validator(mode="after")
    def _eighteen_unique_partners(self):
        if len(self.partners) != 18:
            raise ValueError(f"partners.json must contain exactly 18 records, found {len(self.partners)}")
        ids = [p.partner_id for p in self.partners]
        if len(set(ids)) != len(ids):
            raise ValueError("partners.json contains duplicate partner_id values")
        return self


class Activity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    activity_code: str
    name_key: str
    indicative_cost_min: int
    indicative_cost_max: int
    is_plantation_or_construction: bool


class ActivitiesFile(BaseModel):
    model_config = ConfigDict(extra="allow")

    activities: list[Activity]


class Course(BaseModel):
    model_config = ConfigDict(extra="forbid")

    course_code: str
    name_key: str
    level: Literal["undergraduate", "postgraduate", "diploma"]
    typical_duration_months: int


class CoursesFile(BaseModel):
    model_config = ConfigDict(extra="allow")

    courses: list[Course]


class DocumentEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    name_key: str


class ChecklistItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    mandatory: bool


class DocumentsFile(BaseModel):
    model_config = ConfigDict(extra="allow")

    documents: list[DocumentEntry]
    checklists: dict[str, list[ChecklistItem]]


class I18nBundle(BaseModel):
    model_config = ConfigDict(extra="allow")

    root: dict[str, str]

    @classmethod
    def from_dict(cls, data: dict) -> "I18nBundle":
        if not all(isinstance(v, str) for v in data.values()):
            raise ValueError("i18n bundle must be a flat mapping of key -> string")
        return cls(root=data)
