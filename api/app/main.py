from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.config import settings
from app.db import engine
from app.routers import (
    accounts,
    admin,
    budgets,
    calculators,
    categories,
    countries,
    fx,
    goals,
    imports,
    me,
    remittances,
    reports,
    transactions,
)

settings.check()

app = FastAPI(
    title="Finance Copilot API",
    version="0.1.0",
    description="Track, plan, learn and practise across every country you live and bank in. "
    "Information and simulations only, never financial advice.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (
    countries,
    me,
    accounts,
    categories,
    transactions,
    imports,
    budgets,
    reports,
    remittances,
    goals,
    calculators,
    fx,
    admin,
):
    app.include_router(r.router)


@app.get("/health", tags=["ops"])
def health():
    """Liveness: the process is up."""
    return {"status": "ok"}


@app.get("/ready", tags=["ops"])
def ready():
    """Readiness: the database answers."""
    with engine.connect() as conn:
        conn.execute(text("select 1"))
    return {"status": "ready"}
