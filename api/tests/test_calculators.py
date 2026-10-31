from decimal import Decimal as D

from app.calculators import engine


def test_compound_growth_zero_rate_is_plain_saving():
    r = engine.compound_growth(D("10000"), D("100"), D("0"), 1)
    assert r["final_value"] == D("11200.00")
    assert r["total_growth"] == D("0.00")
    assert len(r["series"]) == 2


def test_compound_growth_monthly_compounding():
    # 1000 at 12% a year, compounded monthly: 1000 * 1.01^12
    r = engine.compound_growth(D("1000"), D("0"), D("12"), 1)
    assert r["final_value"] == D("1126.83")


def test_regular_investing_matches_annuity_formula():
    # 1000 a month at 1% a month for 12 months: 1000 * (1.01^12 - 1) / 0.01
    r = engine.regular_investing(D("1000"), D("12"), 1)
    assert r["final_value"] == D("12682.50")
    assert r["total_invested"] == D("12000.00")


def test_regular_investing_step_up_raises_contributions_each_year():
    r = engine.regular_investing(D("1000"), D("0"), 2, annual_step_up_pct=D("10"))
    assert r["total_invested"] == D("25200.00")  # 12 x 1000 + 12 x 1100


def test_loan_repayment_known_emi():
    r = engine.loan_repayment(D("100000"), D("12"), 1)
    assert r["monthly_payment"] == D("8884.88")
    assert r["months"] == 12
    assert r["total_interest"] == D("6618.55")
    assert r["schedule"][-1]["balance"] == D("0.00")


def test_loan_repayment_zero_interest():
    r = engine.loan_repayment(D("1200"), D("0"), 1)
    assert r["monthly_payment"] == D("100.00")
    assert r["total_interest"] == D("0.00")


def test_extra_repayments_shorten_loan_and_save_interest():
    r = engine.loan_repayment(D("500000"), D("6"), 30, extra_monthly=D("500"))
    extra = r["with_extra"]
    assert extra["months"] < r["months"]
    assert extra["interest_saved"] > 0
    assert extra["months_saved"] == r["months"] - extra["months"]


def test_emergency_fund_gap_and_coverage():
    r = engine.emergency_fund(D("3000"), 6, D("9000"))
    assert r["target"] == D("18000.00")
    assert r["gap"] == D("9000.00")
    assert r["months_covered"] == D("3.0")
    assert r["on_track"] is False


def test_emergency_fund_without_expense_data():
    r = engine.emergency_fund(D("0"), 6, D("500"))
    assert r["months_covered"] is None
