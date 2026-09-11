"""Quarterly instalment calculator (CLAUDE.md §4, BACKEND_BRIEF.md Step 1).

Pure, no I/O. Decimal throughout; converted to int only at the boundary.

`total_outgo` is defined as `instalment * number_of_instalments` and must never
be recomputed another way, or the response becomes internally inconsistent
across the three headline numbers.
"""
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal


def _round(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


@dataclass(frozen=True)
class InstalmentResult:
    number_of_instalments: int
    principal_at_repayment_start: int
    instalment: int
    monthly_equivalent: int
    total_outgo: int
    total_interest: int


@dataclass(frozen=True)
class ScheduleRow:
    n: int
    instalment: int
    interest: int
    principal: int
    balance: int


def compute(
    sanctioned: Decimal,
    annual_rate: Decimal,
    total_period_months: int,
    moratorium_months: int,
    tenure_includes_moratorium: bool,
    moratorium_treatment: str = "capitalise",
) -> InstalmentResult:
    if tenure_includes_moratorium:
        repayment_months = total_period_months - moratorium_months
    else:
        repayment_months = total_period_months

    n = repayment_months // 3

    if moratorium_treatment == "capitalise":
        principal = sanctioned * (
            1 + annual_rate / Decimal(100) * Decimal(moratorium_months) / Decimal(12)
        )
    else:
        principal = sanctioned

    principal_rounded = _round(principal)

    i = (annual_rate / Decimal(100)) / Decimal(4)
    growth = (1 + i) ** n
    instalment_exact = Decimal(principal_rounded) * i * growth / (growth - 1)
    instalment = _round(instalment_exact)

    total_outgo = instalment * n
    total_interest = total_outgo - int(sanctioned)
    monthly_equivalent = _round(Decimal(instalment) / Decimal(3))

    return InstalmentResult(
        number_of_instalments=n,
        principal_at_repayment_start=principal_rounded,
        instalment=instalment,
        monthly_equivalent=monthly_equivalent,
        total_outgo=total_outgo,
        total_interest=total_interest,
    )


def build_schedule(
    principal: int,
    annual_rate: Decimal,
    instalment: int,
    n: int,
) -> list[ScheduleRow]:
    """Per-instalment amortisation. The final row absorbs rounding residue so
    the closing balance is exactly zero."""
    i = (annual_rate / Decimal(100)) / Decimal(4)
    balance = Decimal(principal)
    rows: list[ScheduleRow] = []

    for k in range(1, n + 1):
        interest_component = _round(balance * i)
        if k < n:
            principal_component = instalment - interest_component
            balance -= Decimal(principal_component)
            rows.append(
                ScheduleRow(
                    n=k,
                    instalment=instalment,
                    interest=interest_component,
                    principal=principal_component,
                    balance=_round(balance),
                )
            )
        else:
            # final instalment: absorb rounding residue, close the balance exactly
            principal_component = _round(balance)
            final_instalment = interest_component + principal_component
            rows.append(
                ScheduleRow(
                    n=k,
                    instalment=final_instalment,
                    interest=interest_component,
                    principal=principal_component,
                    balance=0,
                )
            )

    return rows
