"""MediKiosk API. `uvicorn app.main:app --reload`.

Startup does three things and says so in the log: create the schema (SQLite dev only; Alembic
owns anything else), seed the terminology tables so the closed-vocabulary guard has something
to verify against, and sweep any session that expired while the process was down.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.api import (
    routes_demo,
    routes_dialogue,
    routes_documents,
    routes_patient,
    routes_physician,
    routes_session,
    routes_system,
)
from app.auth import mock_idp
from app.core.config import settings
from app.core.errors import MediKioskError
from app.core.logging import configure_logging, get_logger
from app.db.session import create_all, get_sessionmaker
from app.fhir.outcomes import outcome_from_error

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()

    # Which database is actually behind this process, said out loud. A demo that silently
    # ran on an empty local SQLite file while everyone believed it was on Supabase would
    # look identical right up to the moment the patient history came back empty.
    log.info(
        "startup.database",
        backend=settings.database_backend,
        host=settings.database_host,  # host only; the URL carries the password
    )
    # The guard protects a demo or a deployment from silently running on an empty local
    # file. A TEST run wants SQLite by definition — an in-memory database per test is the
    # whole reason the suite needs no network — so the guard must not fire there. Without
    # this exemption, setting REQUIRE_SUPABASE in a developer's .env broke every test that
    # starts the app, which is a booby trap, not a safety feature.
    if settings.environment != "test" and settings.require_supabase and not settings.is_supabase:
        raise RuntimeError(
            f"REQUIRE_SUPABASE is set but DATABASE_URL points at {settings.database_backend}. "
            "Refusing to start on the wrong database — set DATABASE_URL to the Supabase "
            "connection string, or unset REQUIRE_SUPABASE for a local run."
        )

    if settings.is_sqlite:
        await create_all()
        log.info("startup.schema", mode="create_all", note="SQLite dev only")
    else:
        # Postgres is built by Alembic and nothing else. `create_all()` here would paper
        # over a missing migration, which is precisely how the durable schema went missing.
        log.info("startup.schema", mode="alembic", note="run `alembic upgrade head`")

    async with get_sessionmaker()() as session:
        from app.terminology.store import seed_all

        loaded = await seed_all(session)
        await session.commit()
        log.info("startup.terminology", systems=len(loaded))

        from app.modules.encounter.seed import seed_demo_patient

        seeded = await seed_demo_patient(session)
        await session.commit()
        log.info("startup.demo_patient", **{k: v for k, v in seeded.items() if k != "documents"})

        from app.modules.consent.session import sweep_expired

        swept = await sweep_expired(session)
        await session.commit()
        if swept:
            log.info("startup.sweep", purged=len(swept))

    from app.llm.registry import describe as describe_llm

    log.info("startup.ready", version=__version__, llm=describe_llm()["name"])
    yield


app = FastAPI(
    title="MediKiosk",
    version=__version__,
    description=(
        "Patient-facing clinical intake for SIH26047. Produces a structured, source-linked "
        "clinical HISTORY. It does not diagnose. See GET /about for the full invariant list."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(MediKioskError)
async def domain_error_handler(request: Request, exc: MediKioskError) -> JSONResponse:
    """Every domain error becomes a FHIR OperationOutcome. Ported behaviour from SIH 25026."""
    log.warning(
        "request.error",
        path=request.url.path,
        error=type(exc).__name__,
        detail=exc.message[:200],
    )
    return JSONResponse(
        status_code=exc.http_status,
        content=outcome_from_error(exc).model_dump(mode="json", exclude_none=True),
    )


app.include_router(routes_system.router)
app.include_router(routes_system.stub_router)
app.include_router(routes_session.router)
app.include_router(routes_dialogue.router)
app.include_router(routes_documents.router)
app.include_router(routes_physician.router)
app.include_router(routes_demo.router)
app.include_router(routes_patient.router)
app.include_router(mock_idp.router)


@app.get("/")
async def root() -> dict[str, Any]:
    return {
        "name": "MediKiosk",
        "version": __version__,
        "docs": "/docs",
        "about": "/about",
        "notice": "Produces a clinical history, never a diagnosis.",
    }
