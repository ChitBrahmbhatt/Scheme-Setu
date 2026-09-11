"""Partner filtering, routing classification and ordering
(CLAUDE.md §6, BACKEND_BRIEF.md Step 6).

Pure, no I/O, no network. Partner data itself is SIMULATED (data/partners.json);
this module only applies deterministic filtering/threshold logic to it and
never presents it as verified real-world availability.

Thresholds (CLAUDE.md §6, confirmed literal — exclusive lower bound on overdue):

    NOT_ACCEPTING   overdue_ratio_pct > 25   or  fund_utilisation_pct >= 100
    LIMITED         15 < overdue_ratio_pct <= 25  or  85 <= fund_utilisation_pct < 100
    ACCEPTING       otherwise

When the two indicators disagree, the more restrictive status wins.
"""
from dataclasses import dataclass
from typing import Literal

from app.data_models import Partner
from app.engine import geo
from app.engine.eligibility import Reason

RoutingStatus = Literal["ACCEPTING", "LIMITED", "NOT_ACCEPTING"]

OVERDUE_LIMITED_LOWER_EXCLUSIVE = 15
OVERDUE_NOT_ACCEPTING_THRESHOLD = 25
UTILISATION_LIMITED_LOWER_INCLUSIVE = 85
UTILISATION_NOT_ACCEPTING_THRESHOLD = 100

_SEVERITY = {"ACCEPTING": 0, "LIMITED": 1, "NOT_ACCEPTING": 2}


def base_scheme_id(scheme_id: str) -> str:
    """'NSFDC_UNY.SFB' -> 'NSFDC_UNY'; plain ids pass through unchanged."""
    return scheme_id.split(".", 1)[0]


def filter_by_scheme(partners: list[Partner], scheme_id: str) -> list[Partner]:
    base = base_scheme_id(scheme_id)
    return [p for p in partners if base in p.schemes_supported]


def _overdue_classification(overdue_ratio_pct: float) -> tuple[RoutingStatus, Reason]:
    if overdue_ratio_pct > OVERDUE_NOT_ACCEPTING_THRESHOLD:
        return "NOT_ACCEPTING", Reason(
            "OVERDUE_ABOVE_THRESHOLD",
            {"pct": overdue_ratio_pct, "threshold": OVERDUE_NOT_ACCEPTING_THRESHOLD},
        )
    if overdue_ratio_pct > OVERDUE_LIMITED_LOWER_EXCLUSIVE:
        return "LIMITED", Reason("OVERDUE_ELEVATED", {"pct": overdue_ratio_pct})
    return "ACCEPTING", Reason("OVERDUE_BELOW_THRESHOLD", {"pct": overdue_ratio_pct})


def _utilisation_classification(fund_utilisation_pct: float) -> tuple[RoutingStatus, Reason]:
    if fund_utilisation_pct >= UTILISATION_NOT_ACCEPTING_THRESHOLD:
        return "NOT_ACCEPTING", Reason("UTILISATION_EXHAUSTED", {"pct": fund_utilisation_pct})
    if fund_utilisation_pct >= UTILISATION_LIMITED_LOWER_INCLUSIVE:
        return "LIMITED", Reason("UTILISATION_HIGH", {"pct": fund_utilisation_pct})
    return "ACCEPTING", Reason("UTILISATION_WITHIN_LIMIT", {"pct": fund_utilisation_pct})


@dataclass(frozen=True)
class RoutingClassification:
    status: RoutingStatus
    reasons: list[Reason]


def classify(overdue_ratio_pct: float, fund_utilisation_pct: float) -> RoutingClassification:
    utilisation_status, utilisation_reason = _utilisation_classification(fund_utilisation_pct)
    overdue_status, overdue_reason = _overdue_classification(overdue_ratio_pct)
    status = max((utilisation_status, overdue_status), key=lambda s: _SEVERITY[s])
    return RoutingClassification(status=status, reasons=[utilisation_reason, overdue_reason])


@dataclass(frozen=True)
class LocatedPartner:
    partner: Partner
    distance_km: float | None
    routing: RoutingClassification


def locate(
    partners: list[Partner],
    scheme_id: str,
    user_lat: float | None,
    user_lng: float | None,
    radius_km: float | None,
    district: str | None = None,
    state_code: str | None = None,
) -> list[LocatedPartner]:
    """Filtering order (CLAUDE.md §6): scheme support -> distance -> radius ->
    routing classification. Coordinates are never geocoded or inferred —
    only what's already in data/partners.json and the request is used."""
    supported = filter_by_scheme(partners, scheme_id)

    candidates: list[tuple[Partner, float | None]]
    if user_lat is not None and user_lng is not None:
        candidates = []
        for partner in supported:
            distance = geo.haversine_km(user_lat, user_lng, partner.lat, partner.lng)
            if radius_km is None or distance <= radius_km:
                candidates.append((partner, geo.round_distance_km(distance)))
    else:
        # No coordinates supplied: fall back to district/state matching with
        # no computed distance (never geocoded, never inferred from address).
        candidates = [
            (partner, None)
            for partner in supported
            if (district is None or partner.district == district)
            and (state_code is None or partner.state_code == state_code)
        ]

    return [
        LocatedPartner(
            partner=partner,
            distance_km=distance,
            routing=classify(partner.overdue_ratio_pct, partner.fund_utilisation_pct),
        )
        for partner, distance in candidates
    ]


def sort_and_split(located: list[LocatedPartner]) -> tuple[list[LocatedPartner], list[LocatedPartner]]:
    """ACCEPTING first, then LIMITED, nearest distance first within each group
    (stable sort: exact ties preserve input order rather than inventing a
    tiebreaker). NOT_ACCEPTING partners are split into a separate, excluded
    group and never mixed into the main list."""
    main = [lp for lp in located if lp.routing.status != "NOT_ACCEPTING"]
    excluded = [lp for lp in located if lp.routing.status == "NOT_ACCEPTING"]

    def main_sort_key(lp: LocatedPartner):
        status_rank = 0 if lp.routing.status == "ACCEPTING" else 1
        distance_rank = lp.distance_km if lp.distance_km is not None else 0.0
        return (status_rank, distance_rank)

    main_sorted = sorted(main, key=main_sort_key)
    excluded_sorted = sorted(excluded, key=lambda lp: lp.distance_km if lp.distance_km is not None else 0.0)
    return main_sorted, excluded_sorted
