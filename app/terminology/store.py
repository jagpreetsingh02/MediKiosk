"""Terminology ingestion and lookup. **Adapted from SIH 25026 `app/terminology/store.py`.**

The 25026 version ingested WHO ICD-11 over HTTP and NAMASTE from an Excel release. MediKiosk
does not need the release pipeline — it needs *a loaded table so the guard has something to
verify against* — so this is the ingestion half only, reading the JSON files under
`data/terminology/`.

The rule that carries across intact: terminology content is data. No code string, display name
or mapping is written in Python anywhere in this repo. `tests/test_no_hardcoded_codes.py`
enforces it.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.db.models import CodeSystem, Concept

log = get_logger(__name__)

_PUNCT = re.compile(r"[^\w\s]+", re.UNICODE)
_SPACE = re.compile(r"\s+")


def normalize(text: str) -> str:
    """Fold for matching only. Never used for display (ADR-0004, carried across)."""
    folded = unicodedata.normalize("NFKD", text.casefold())
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
    return _SPACE.sub(" ", _PUNCT.sub(" ", folded)).strip()


async def load_codesystem_file(session: AsyncSession, path: Path) -> CodeSystem:
    # Blocking file reads inside an async function, deliberately: this runs once at startup
    # over three small JSON files before the server accepts traffic. Pushing it to a thread
    # pool would add machinery to a path where nothing is waiting on the event loop.
    payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))  # noqa: ASYNC240
    url, version = payload["url"], payload["version"]

    existing = (
        (
            await session.execute(
                select(CodeSystem).where(CodeSystem.url == url, CodeSystem.version == version)
            )
        )
        .scalars()
        .first()
    )
    if existing is not None:
        return existing

    checksum = hashlib.sha256(path.read_bytes()).hexdigest()  # noqa: ASYNC240
    cs = CodeSystem(
        url=url,
        name=payload["name"],
        title=payload.get("title"),
        version=version,
        publisher=payload.get("publisher"),
        module=payload.get("module"),
        is_active=True,
        checksum=checksum,
    )
    session.add(cs)
    await session.flush()

    for item in payload["concepts"]:
        session.add(
            Concept(
                code_system_id=cs.id,
                code=item["code"],
                display=item["display"],
                display_normalized=normalize(item["display"]),
                class_kind=item.get("classKind", "category"),
                is_selectable=item.get("selectable", True),
                module=payload.get("module"),
                definition=item.get("definition"),
                foundation_uri=item.get("foundationUri"),
                synonyms=item.get("synonyms"),
            )
        )
    await session.flush()
    log.info("terminology.loaded", system=url, version=version, concepts=len(payload["concepts"]))
    return cs


def is_codesystem_file(path: Path) -> bool:
    """A CodeSystem file declares a url, a version and concepts.

    The seed directory also holds non-CodeSystem data (reference-ranges.json), so the
    seeder identifies its input by SHAPE rather than by globbing every .json and hoping.
    """
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    return isinstance(payload, dict) and {"url", "version", "concepts"} <= set(payload)


async def seed_all(session: AsyncSession, directory: str | None = None) -> dict[str, int]:
    """Load every CodeSystem JSON in the seed directory. Idempotent."""
    seed_dir = settings.path(directory or settings.terminology_seed_dir)
    loaded: dict[str, int] = {}
    for path in sorted(seed_dir.glob("*.json")):
        if not is_codesystem_file(path):
            log.debug("terminology.skipped", file=path.name, reason="not a CodeSystem")
            continue
        cs = await load_codesystem_file(session, path)
        count = len(
            (await session.execute(select(Concept.id).where(Concept.code_system_id == cs.id)))
            .scalars()
            .all()
        )
        loaded[f"{cs.url}|{cs.version}"] = count
    return loaded


async def lookup(session: AsyncSession, system: str, term: str, *, limit: int = 5) -> list[Concept]:
    """Normalised-substring lookup. Deliberately dumb, and deliberately allowed to find nothing.

    Fuzzy scoring lives in the 25026 service behind pg_trgm; porting it here would add a
    Postgres dependency to a code path whose correct answer is very often "unmapped".
    """
    key = normalize(term)
    if len(key) < 3:
        return []
    cs = (
        (
            await session.execute(
                select(CodeSystem)
                .where(CodeSystem.url == system, CodeSystem.is_active.is_(True))
                .order_by(CodeSystem.created_at.desc())
            )
        )
        .scalars()
        .first()
    )
    if cs is None:
        return []
    rows = (
        (await session.execute(select(Concept).where(Concept.code_system_id == cs.id)))
        .scalars()
        .all()
    )

    exact = [c for c in rows if c.display_normalized == key]
    contains = [
        c
        for c in rows
        if c is not None and c.display_normalized and key in c.display_normalized and c not in exact
    ]
    reverse = [
        c
        for c in rows
        if c.display_normalized
        and c.display_normalized in key
        and c not in exact
        and c not in contains
    ]
    return (exact + contains + reverse)[:limit]
