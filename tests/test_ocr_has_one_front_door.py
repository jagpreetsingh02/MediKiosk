"""OCR has one way in, and this test is what keeps it that way.

⛔ THE FAILURE THIS PREVENTS ALREADY HAPPENED.

`app/modules/encounter/seed.py` imported `get_ocr_backend` and `extract_entities` directly and
called them in-process at application startup. The three dated lab reports in the demo
patient's history were produced that way, and on that basis they were described as having gone
"through the actual OCR pipeline".

They had not, in any sense that mattered. That path skipped:

    the HTTP route          no multipart, no UploadFile, no boundary handling
    the consent gate        `documents` scope never checked
    the size limit          `max_upload_bytes` never applied
    the browser             no file picker, no camera, no upload at all
    pipeline.py             the module that ties reading to recording

A private back door into OCR is how a project convinces itself a feature works when only a
fragment of it does — and the fragment that was working was the fragment nobody doubted.

So: `pipeline.py` is the only module permitted to import an OCR backend. Everything else goes
through `ingest()` (for a session) or `read_and_extract()` (for anything else). This test
scans the source tree and fails the build on any new back door.

It is a source scan rather than a runtime check on purpose. The bug was not a call that
behaved wrongly; it was a call that behaved *correctly in isolation* while bypassing every
guarantee around it. Only the import graph shows that.
"""

from __future__ import annotations

import ast
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"

#: The one module allowed to reach an OCR engine.
FRONT_DOOR = APP / "modules" / "documents" / "pipeline.py"

#: Modules that ARE the OCR layer, and so may import each other freely.
OCR_LAYER = {
    APP / "modules" / "documents" / "backends.py",
    APP / "modules" / "documents" / "entities.py",
    APP / "modules" / "documents" / "imaging.py",
    APP / "modules" / "documents" / "render.py",
    APP / "modules" / "documents" / "timeline.py",
    APP / "modules" / "documents" / "ranges.py",
}

#: Names that mean "I am reading a document myself".
BACKDOOR_NAMES = {"get_ocr_backend", "read_document", "extract_entities", "backend_for"}

#: `/about` reports which engines are installed. That is a capability listing, not a read.
ALLOWED_NAMES = {"available_backends"}


def _code_only(path: Path) -> str:
    """The file with comments and docstrings removed.

    Necessary because these assertions describe code, and the comments here deliberately QUOTE
    the very patterns being banned in order to explain why. Matching against prose would fail
    on the explanation rather than on the offence — and the fix for that would be to stop
    explaining, which is the wrong direction.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            if isinstance(node.value.value, str):
                node.value.value = ""  # a docstring
    stripped = ast.unparse(tree)
    return "\n".join(
        line for line in stripped.splitlines() if not line.strip().startswith("#")
    )


def _imports(path: Path) -> list[tuple[str, str, int]]:
    """(module, imported_name, lineno) for every import in the file."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[tuple[str, str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                found.append((node.module, alias.name, node.lineno))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                found.append((alias.name, alias.name.rsplit(".", 1)[-1], node.lineno))
    return found


def test_only_the_pipeline_imports_an_ocr_backend() -> None:
    offenders: list[str] = []

    for path in sorted(APP.rglob("*.py")):
        if path == FRONT_DOOR or path in OCR_LAYER:
            continue
        for module, name, lineno in _imports(path):
            if name in ALLOWED_NAMES:
                continue
            reaches_ocr = "documents.backends" in module or "documents.entities" in module
            if reaches_ocr and name in BACKDOOR_NAMES:
                offenders.append(
                    f"{path.relative_to(APP.parent)}:{lineno} imports {name} from {module}"
                )

    assert not offenders, (
        "OCR must be reached through pipeline.ingest() or pipeline.read_and_extract(), "
        "never by importing an engine directly. A private path around the pipeline skips the "
        "consent gate, the size limit and the upload route — which is exactly how three "
        "seeded lab reports came to be described as having been through OCR when they had "
        "not.\n  " + "\n  ".join(offenders)
    )


def test_the_seed_goes_through_the_front_door() -> None:
    """The specific regression, named, because this file is where someone will look."""
    source = (APP / "modules" / "encounter" / "seed.py").read_text(encoding="utf-8")
    assert "read_and_extract" in source, "seed.py no longer routes OCR through pipeline.py"
    for backdoor in ("get_ocr_backend(", "extract_entities("):
        # Substring rather than import check: a call is what did the damage.
        offending = [
            line
            for line in source.splitlines()
            if backdoor in line and not line.strip().startswith("#")
        ]
        assert not offending, f"seed.py calls {backdoor} directly again: {offending}"


def test_the_front_door_is_actually_a_door() -> None:
    """Guard against the test above passing because the function was quietly deleted."""
    from app.modules.documents import pipeline

    assert hasattr(pipeline, "read_and_extract")
    assert hasattr(pipeline, "ingest")


def test_the_upload_route_enforces_the_size_limit() -> None:
    """A limit that exists in config and is never applied is not a limit.

    `max_upload_bytes` was defined for a long time while the route did `await file.read()`
    with no check at all. This asserts the route both consults the setting and does so before
    holding the whole body — the header check and the streaming check are separate guarantees
    and losing either one matters.
    """
    source = _code_only(APP / "api" / "routes_documents.py")

    assert "max_upload_bytes" in source, "the upload route ignores the size limit again"
    assert "content-length" in source.lower(), (
        "the cheap check is gone — an oversized upload is now read before being refused"
    )
    assert "await file.read(" in source and "_UPLOAD_CHUNK_BYTES" in source, (
        "the body is no longer read in bounded chunks"
    )
    assert "await file.read()" not in source, (
        "the whole body is being read into memory before the limit is applied"
    )
