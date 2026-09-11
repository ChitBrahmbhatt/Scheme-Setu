"""GET /partners (BACKEND_BRIEF.md Step 6, API.md §3).

Orchestration only: parse query params, delegate filtering/distance/routing
to engine/geo.py and engine/partner_routing.py, then shape the frozen
response. Partner data is SIMULATED end to end and is never presented as
verified real-world availability.
"""
import uuid

from fastapi import APIRouter, Query

from app.config import get_settings
from app.engine.partner_routing import base_scheme_id, locate, sort_and_split
from app.loader import get_data
from app.errors import ApiError
from app.schemas import (
    ExcludedBlockOut,
    ExcludedPartnerOut,
    PartnerIndicatorsOut,
    PartnerOut,
    PartnersQueryOut,
    PartnersResponse,
    ReasonOut,
)

router = APIRouter()


def _new_request_id() -> str:
    return f"req_{uuid.uuid4().hex[:13]}"


def _validate_scheme_id(scheme_id: str) -> None:
    data = get_data()
    base = base_scheme_id(scheme_id)
    scheme = next((s for s in data.schemes.schemes if s.scheme_id == base), None)
    if scheme is None:
        raise ApiError("NOT_FOUND", f"Unknown scheme_id '{scheme_id}'.", field="scheme_id", status_code=404)

    if "." in scheme_id:
        variant_id = scheme_id.split(".", 1)[1]
        variant_ids = [v.variant_id for v in (scheme.channel_variants or [])]
        if variant_id not in variant_ids:
            raise ApiError(
                "VALIDATION_ERROR",
                f"'{scheme_id}' is not a valid channel variant of '{base}'.",
                field="scheme_id",
            )


@router.get("/partners", response_model=PartnersResponse)
def get_partners(
    scheme_id: str = Query(...),
    lat: float | None = Query(default=None, ge=-90, le=90),
    lng: float | None = Query(default=None, ge=-180, le=180),
    state_code: str | None = Query(default=None),
    district: str | None = Query(default=None),
    radius_km: float | None = Query(default=None, gt=0, le=1000),
    limit: int | None = Query(default=None, gt=0, le=100),
) -> PartnersResponse:
    _validate_scheme_id(scheme_id)

    has_coordinates = lat is not None and lng is not None
    has_district = state_code is not None and district is not None
    if not has_coordinates and not has_district:
        raise ApiError(
            "VALIDATION_ERROR",
            "Either lat/lng or state_code/district must be provided.",
            field="lat",
        )

    data = get_data()
    settings = get_settings()
    effective_radius = None
    if has_coordinates:
        effective_radius = radius_km if radius_km is not None else settings.default_radius_km

    located = locate(
        partners=data.partners.partners,
        scheme_id=scheme_id,
        user_lat=lat,
        user_lng=lng,
        radius_km=effective_radius,
        district=district,
        state_code=state_code,
    )
    main_sorted, excluded_sorted = sort_and_split(located)

    if limit is not None:
        main_sorted = main_sorted[:limit]

    partners_out = [
        PartnerOut(
            partner_id=lp.partner.partner_id,
            name=lp.partner.name,
            branch_label=lp.partner.branch_label,
            type=lp.partner.type,
            address=lp.partner.address,
            district=lp.partner.district,
            state=lp.partner.state,
            state_code=lp.partner.state_code,
            pincode=lp.partner.pincode,
            lat=lp.partner.lat,
            lng=lp.partner.lng,
            phone=lp.partner.phone,
            distance_km=lp.distance_km,
            schemes_supported=lp.partner.schemes_supported,
            routing_status=lp.routing.status,
            routing_reasons=[ReasonOut(code=r.code, params=r.params) for r in lp.routing.reasons],
            indicators=PartnerIndicatorsOut(
                fund_utilisation_pct=lp.partner.fund_utilisation_pct,
                overdue_ratio_pct=lp.partner.overdue_ratio_pct,
                avg_sanction_days=lp.partner.avg_sanction_days,
            ),
            data_tier=lp.partner.data_tier,
        )
        for lp in main_sorted
    ]

    excluded_out = [
        ExcludedPartnerOut(
            partner_id=lp.partner.partner_id,
            name=lp.partner.name,
            branch_label=lp.partner.branch_label,
            distance_km=lp.distance_km,
            type=lp.partner.type,
            routing_status=lp.routing.status,
            routing_reasons=[ReasonOut(code=r.code, params=r.params) for r in lp.routing.reasons],
            data_tier=lp.partner.data_tier,
        )
        for lp in excluded_sorted
    ]

    return PartnersResponse(
        request_id=_new_request_id(),
        ruleset_version=data.schemes.ruleset_version,
        query=PartnersQueryOut(
            scheme_id=scheme_id,
            lat=lat,
            lng=lng,
            state_code=state_code,
            district=district,
            radius_km=effective_radius,
            limit=limit,
        ),
        data_tier="SIMULATED",
        disclaimer_key="partners.dataset_simulated",
        partners=partners_out,
        excluded=ExcludedBlockOut(count=len(excluded_out), items=excluded_out),
    )
