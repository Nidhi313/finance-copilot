"""Sample data for the local demo user, so the app has something to show on first
run. Only used locally; refuses to run if the demo user already has accounts.

    python -m app.cli demo-data
"""

import random
from datetime import date, timedelta
from decimal import Decimal as D

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.countries.context import get_country_context
from app.models import Account, Budget, Category, Goal, Remittance, Transaction, User, UserCountryLink
from app.services.categorise import Categoriser


def _month_days(months_back: int) -> list[date]:
    today = date.today()
    first = date(today.year, today.month, 1)
    idx = first.year * 12 + first.month - 1 - months_back
    start = date(idx // 12, idx % 12 + 1, 1)
    end = (
        today
        if months_back == 0
        else (date(start.year + (start.month // 12), start.month % 12 + 1, 1) - timedelta(days=1))
    )
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def load_demo_data(db: Session) -> str:
    user = db.scalar(select(User).where(User.email == settings.demo_user_email))
    if user is None:
        user = User(email=settings.demo_user_email, display_name="Demo user", home_currency="AUD")
        db.add(user)
        db.flush()
    if db.scalar(select(Account.id).where(Account.user_id == user.id).limit(1)):
        return "Demo user already has accounts; nothing added."
    rng = random.Random(42)
    user.home_currency = "AUD"
    user.active_country_code = "AU"
    db.add_all(
        [
            UserCountryLink(user_id=user.id, country_code="AU", relationships=["lives_here", "tax_resident"]),
            UserCountryLink(
                user_id=user.id, country_code="IN", relationships=["citizen", "holds_accounts", "sends_money_to"]
            ),
        ]
    )
    everyday = Account(
        user_id=user.id,
        country_code="AU",
        name="Everyday",
        type="bank",
        currency="AUD",
        institution="CommBank",
        opening_balance=D("2400"),
    )
    savings = Account(
        user_id=user.id,
        country_code="AU",
        name="Rainy day savings",
        type="savings",
        currency="AUD",
        institution="ING",
        opening_balance=D("6500"),
    )
    superfund = Account(
        user_id=user.id,
        country_code="AU",
        name="Super",
        type="super",
        currency="AUD",
        institution="AustralianSuper",
        opening_balance=D("21300"),
    )
    nre = Account(
        user_id=user.id,
        country_code="IN",
        name="NRE account",
        type="nre",
        currency="INR",
        institution="HDFC Bank",
        opening_balance=D("250000"),
    )
    ppf = Account(
        user_id=user.id,
        country_code="IN",
        name="PPF",
        type="ppf",
        currency="INR",
        institution="SBI",
        opening_balance=D("180000"),
    )
    db.add_all([everyday, savings, superfund, nre, ppf])
    db.flush()

    au = Categoriser(db, user.id, get_country_context(db, "AU"))
    ind = Categoriser(db, user.id, get_country_context(db, "IN"))
    cats = {c.name: c.id for c in db.scalars(select(Category).where(Category.user_id.is_(None)))}
    txns = []

    def add(acc, d, desc, amount, cat=None, categoriser=au):
        txns.append(
            Transaction(
                user_id=user.id,
                account_id=acc.id,
                date=d,
                description=desc,
                amount=D(amount),
                category_id=cats.get(cat) if cat else categoriser.category_for(desc),
            )
        )

    for back in (3, 2, 1, 0):
        days = _month_days(back)
        for d in days:
            if d.day in (14, 28):
                add(everyday, d, "SALARY ACME PTY LTD", "3150.00")
            if d.day == 1:
                add(everyday, d, "RENT PAYMENT RAY WHITE", "-2080.00", "Rent")
            if d.weekday() == 5:
                add(
                    everyday,
                    d,
                    rng.choice(["WOOLWORTHS 1234 SYDNEY", "COLES 0567 STRATHFIELD", "ALDI STORES"]),
                    f"-{rng.uniform(60, 140):.2f}",
                )
            if d.weekday() in (2, 6):
                add(
                    everyday,
                    d,
                    rng.choice(["UBER EATS", "MENULOG", "CAFE ON KING ST"]),
                    f"-{rng.uniform(15, 45):.2f}",
                    None if rng.random() < 0.8 else "Eating out",
                )
            if d.weekday() == 0:
                add(everyday, d, "OPAL TRANSPORT", f"-{rng.uniform(20, 35):.2f}")
            if d.day == 5:
                add(everyday, d, "NETFLIX.COM", "-18.99")
                add(everyday, d, "OPTUS MOBILE", "-45.00")
            if d.day == 20:
                add(everyday, d, "TRANSFER TO SAVINGS", "-400.00", "Transfers")
                add(savings, d, "TRANSFER FROM EVERYDAY", "400.00", "Transfers")
            if d.day == 12:
                add(nre, d, "NEFT FROM ABROAD", "55000.00", "Transfers", ind)
            if d.day == 15:
                add(nre, d, "BILLDESK AIRTEL POSTPAID", "-799.00", None, ind)
                add(nre, d, "AMAZON PAY INDIA", f"-{rng.uniform(1200, 4500):.2f}", None, ind)
            if d.day == 25:
                add(nre, d, "TO PARENTS FAMILY SUPPORT", "-30000.00", "Gifts and family support", ind)
        if days and back > 0:
            add(everyday, days[-1], "CHEMIST WAREHOUSE", f"-{rng.uniform(15, 60):.2f}")
    db.add_all(txns)

    for name, amount in (("Groceries", "600"), ("Eating out", "250"), ("Transport", "150"), ("Entertainment", "60")):
        db.add(Budget(user_id=user.id, country_code="AU", category_id=cats[name], amount=D(amount), currency="AUD"))

    today = date.today()
    for back, sent, fee, received, provider in (
        (80, "1010", "10", "54300", "Big bank transfer"),
        (50, "1004", "4", "55150", "Wise"),
        (20, "1015", "15", "53800", "Big bank transfer"),
    ):
        db.add(
            Remittance(
                user_id=user.id,
                date=today - timedelta(days=back),
                from_country_code="AU",
                to_country_code="IN",
                from_currency="AUD",
                to_currency="INR",
                amount_sent=D(sent),
                fee=D(fee),
                amount_received=D(received),
                provider=provider,
            )
        )

    db.add(
        Goal(
            user_id=user.id,
            name="Trip home in December",
            target_amount=D("9000"),
            currency="AUD",
            target_date=date(today.year + (1 if today.month == 12 else 0), 12, 1),
            account_id=savings.id,
        )
    )
    db.add(
        Goal(
            user_id=user.id,
            name="Parents' medical fund",
            target_amount=D("500000"),
            currency="INR",
            account_id=None,
            saved_amount=D("120000"),
        )
    )
    db.commit()
    return f"Added demo data: 5 accounts, {len(txns)} transactions, 4 budgets, 3 transfers, 2 goals."
