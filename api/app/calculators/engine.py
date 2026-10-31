"""Planning calculators. Pure functions of their inputs: no database, no country
branches. A country pack only changes labels, defaults and disclaimer text.

Conventions: monthly compounding at annual_rate / 12, contributions at the end
of each month, results rounded to cents only at the end."""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")


def _r(x: Decimal) -> Decimal:
    return x.quantize(CENT, rounding=ROUND_HALF_UP)


def _monthly(rate_pct: Decimal) -> Decimal:
    return rate_pct / Decimal(100) / Decimal(12)


@dataclass
class YearPoint:
    year: int
    contributed: Decimal
    value: Decimal


def compound_growth(principal: Decimal, monthly_contribution: Decimal, annual_rate_pct: Decimal, years: int) -> dict:
    r = _monthly(annual_rate_pct)
    value = principal
    contributed = principal
    series = [YearPoint(0, _r(contributed), _r(value))]
    for month in range(1, years * 12 + 1):
        value = value * (1 + r) + monthly_contribution
        contributed += monthly_contribution
        if month % 12 == 0:
            series.append(YearPoint(month // 12, _r(contributed), _r(value)))
    return {
        "final_value": _r(value),
        "total_contributed": _r(contributed),
        "total_growth": _r(value - contributed),
        "series": series,
    }


def regular_investing(
    monthly_amount: Decimal, annual_return_pct: Decimal, years: int, annual_step_up_pct: Decimal = Decimal(0)
) -> dict:
    """Same amount every month, optionally raised once a year by a step-up percentage."""
    r = _monthly(annual_return_pct)
    step = Decimal(1) + annual_step_up_pct / Decimal(100)
    value = Decimal(0)
    invested = Decimal(0)
    amount = monthly_amount
    series = [YearPoint(0, Decimal("0.00"), Decimal("0.00"))]
    for month in range(1, years * 12 + 1):
        value = value * (1 + r) + amount
        invested += amount
        if month % 12 == 0:
            series.append(YearPoint(month // 12, _r(invested), _r(value)))
            amount = amount * step
    return {
        "final_value": _r(value),
        "total_invested": _r(invested),
        "total_growth": _r(value - invested),
        "series": series,
    }


def emergency_fund(monthly_expenses: Decimal, months_target: int, current_savings: Decimal) -> dict:
    target = monthly_expenses * months_target
    gap = max(Decimal(0), target - current_savings)
    covered = (current_savings / monthly_expenses) if monthly_expenses > 0 else None
    return {
        "target": _r(target),
        "current_savings": _r(current_savings),
        "gap": _r(gap),
        "months_covered": covered.quantize(Decimal("0.1")) if covered is not None else None,
        "on_track": gap == 0,
    }


def loan_repayment(
    principal: Decimal, annual_rate_pct: Decimal, years: int, extra_monthly: Decimal = Decimal(0)
) -> dict:
    n = years * 12
    r = _monthly(annual_rate_pct)
    if r == 0:
        payment = principal / n
    else:
        growth = (1 + r) ** n
        payment = principal * r * growth / (growth - 1)
    payment_rounded = _r(payment)

    def run(extra: Decimal) -> tuple[int, Decimal, list[dict]]:
        balance = principal
        interest_total = Decimal(0)
        months = 0
        schedule = []
        while balance > CENT / 2 and months < n:
            months += 1
            interest = balance * r
            pay = min(payment + extra, balance + interest)
            balance = balance + interest - pay
            interest_total += interest
            if months % 12 == 0 or balance <= CENT / 2:
                schedule.append(
                    {
                        "month": months,
                        "balance": _r(max(balance, Decimal(0))),
                        "interest_paid_to_date": _r(interest_total),
                    }
                )
        return months, interest_total, schedule

    base_months, base_interest, base_schedule = run(Decimal(0))
    result = {
        "monthly_payment": payment_rounded,
        "total_interest": _r(base_interest),
        "total_paid": _r(principal + base_interest),
        "months": base_months,
        "schedule": base_schedule,
        "with_extra": None,
    }
    if extra_monthly > 0:
        months, interest, schedule = run(extra_monthly)
        result["with_extra"] = {
            "monthly_payment": _r(payment + extra_monthly),
            "total_interest": _r(interest),
            "months": months,
            "months_saved": base_months - months,
            "interest_saved": _r(base_interest - interest),
            "schedule": schedule,
        }
    return result
