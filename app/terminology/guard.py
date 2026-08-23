"""⛔ THE CLOSED-VOCABULARY GUARD — the invariant this whole service rests on.

No code leaves this service unless it was **read from a loaded CodeSystem at a pinned
version**. Codes are retrieved, never generated, never string-formatted, never inferred.

`emit_coding()` is the only sanctioned way to construct a FHIR Coding anywhere in this
codebase (`tests/test_guard_is_the_only_emitter.py` enforces that by scanning the source).

There is **no bypass and no force flag**. The absence of one is the feature.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import (
    NotSelectableError,
    UnknownCodeError,
    UnknownSystemError,
    VersionMismatchError,
)
from app.db.models import CodeSystem, Concept
from app.fhir.r4 import Coding

#: ICD-11 classKind values. Only `category` is a diagnosis; the rest are groupings.
EMITTABLE_CLASS_KIND = "category"
GROUPING_CLASS_KINDS = frozenset({"block", "chapter", "window"})


@dataclass(frozen=True, slots=True)
class VerifiedConcept:
    """A concept proven to exist in a loaded CodeSystem at a known version."""

    concept_id: int
    system: str
    version: str
    code: str
    display: str
    class_kind: str
    module: str | None
    foundation_uri: str | None
    definition: str | None


async def resolve_system(
    session: AsyncSession, system: str, version: str | None = None
) -> CodeSystem:
    """Find the loaded CodeSystem row for `system` (at `version` if pinned)."""
    stmt = select(CodeSystem).where(CodeSystem.url == system)
    if version is not None:
        stmt = stmt.where(CodeSystem.version == version)
    else:
        stmt = stmt.where(CodeSystem.is_active.is_(True))
    stmt = stmt.order_by(CodeSystem.created_at.desc())
    row = (await session.execute(stmt)).scalars().first()
    if row is None:
        if version is not None:
            # Distinguish "system unknown" from "that version is not loaded".
            known = (
                await session.execute(select(CodeSystem.id).where(CodeSystem.url == system))
            ).first()
            if known is not None:
                raise VersionMismatchError(
                    f"CodeSystem {system} is loaded, but not at version {version!r}.",
                    system=system,
                    version=version,
                )
        raise UnknownSystemError(
            f"No CodeSystem loaded for system {system!r}. "
            "Codes can only be emitted from an ingested CodeSystem.",
            system=system,
        )
    return row


async def verify_code(
    session: AsyncSession,
    system: str,
    code: str,
    version: str | None = None,
    *,
    require_selectable: bool = True,
) -> VerifiedConcept:
    """Look the code up. Raise if it is not there, or is not a selectable category.

    This is the single point of truth. Everything else in the service is a caller.
    """
    cs = await resolve_system(session, system, version)
    concept = (
        (
            await session.execute(
                select(Concept).where(Concept.code_system_id == cs.id, Concept.code == code)
            )
        )
        .scalars()
        .first()
    )
    if concept is None:
        raise UnknownCodeError(
            f"Code {code!r} does not exist in {system} at version {cs.version!r}. "
            "This service cannot emit a code it has not ingested.",
            system=system,
            code=code,
            version=cs.version,
        )
    if require_selectable and (
        concept.class_kind != EMITTABLE_CLASS_KIND or not concept.is_selectable
    ):
        raise NotSelectableError(
            f"Code {code!r} in {system} has classKind={concept.class_kind!r} and is a grouping, "
            "not a diagnosis. Only classKind=category entities may be emitted as codes.",
            system=system,
            code=code,
            version=cs.version,
            class_kind=concept.class_kind,
        )
    return VerifiedConcept(
        concept_id=concept.id,
        system=cs.url,
        version=cs.version,
        code=concept.code,
        display=concept.display,
        class_kind=concept.class_kind,
        module=concept.module or cs.module,
        foundation_uri=concept.foundation_uri,
        definition=concept.definition,
    )


async def emit_coding(
    session: AsyncSession,
    system: str,
    code: str,
    version: str | None = None,
    *,
    require_selectable: bool = True,
) -> Coding:
    """Return a FHIR Coding for a code that has been proven to exist. Otherwise raise.

    Do not add a `force`/`trust_me` parameter. Ever.
    """
    verified = await verify_code(
        session, system, code, version, require_selectable=require_selectable
    )
    return coding_from_verified(verified)


def coding_from_verified(verified: VerifiedConcept) -> Coding:
    """Serialise an already-verified concept. Private to the guard by convention."""
    return Coding(
        system=verified.system,
        version=verified.version,
        code=verified.code,
        display=verified.display,
    )


async def emit_codings(
    session: AsyncSession, items: list[tuple[str, str, str | None]]
) -> list[Coding]:
    """Batch helper. Fails loudly on the first unknown code — no partial best-effort output."""
    return [await emit_coding(session, s, c, v) for s, c, v in items]
