"""Everything `app/` imports must be in requirements.txt.

⛔ THE FAILURE THIS PREVENTS HAPPENED IN PRODUCTION, AND THE LOCAL SUITE WAS GREEN.

`reportlab` was sitting in the development venv as an undeclared leftover from some earlier
install. So `import reportlab` worked here, 404 tests passed, ruff and mypy were clean, and
the PDF renderer was verified end to end — while `requirements.txt` never mentioned it. The
Docker image therefore did not have it, and the deploy died at import time:

    File "/app/app/modules/report/pdf.py", line 32, in <module>
        from reportlab.lib.enums import TA_LEFT
    ModuleNotFoundError: No module named 'reportlab'

Nothing available locally could have caught this, because locally the module WAS there. The
only signal is the gap between what the code imports and what the manifest declares — so
that is what this test reads.

It parses the import graph rather than running anything, so it is fast and needs no network.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
REQUIREMENTS = ROOT / "requirements.txt"

#: Import name -> distribution name, where they differ.
ALIASES = {
    "jwt": "pyjwt",
    "yaml": "pyyaml",
    "dotenv": "python-dotenv",
    "multipart": "python-multipart",
    "PIL": "pillow",
    "pypdfium2": "pypdfium2",
    "pydantic_settings": "pydantic-settings",
    "fhir": "fhir.resources",
    "pillow_heif": "pillow-heif",
    "sqlalchemy": "sqlalchemy",
    "asyncpg": "asyncpg",
}

#: Imported lazily inside a try/except with a documented fallback, so absence is HANDLED
#: rather than fatal. `vosk` is the deliberate case: no model on a fresh clone means the
#: confidence is recorded as unavailable, which is the honest branch.
OPTIONAL = {"vosk"}


def _declared() -> set[str]:
    names: set[str] = set()
    for raw in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        name = line.split("[")[0]
        for sep in (">=", "==", "<=", "~=", ">", "<", "!="):
            name = name.split(sep)[0]
        names.add(name.strip().lower().replace("_", "-"))
    return names


def _imported() -> set[str]:
    found: set[str] = set()
    for path in APP.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    found.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                found.add(node.module.split(".")[0])
    return found


def test_every_third_party_import_is_declared() -> None:
    declared = _declared()
    missing: list[str] = []

    for module in sorted(_imported()):
        if module in ("app", "tests") or module in OPTIONAL:
            continue
        if module in sys.stdlib_module_names:
            continue
        distribution = ALIASES.get(module, module).lower().replace("_", "-")
        if distribution not in declared:
            missing.append(f"{module} (expected '{distribution}' in requirements.txt)")

    assert not missing, (
        "app/ imports modules that requirements.txt does not declare. They may be present in "
        "your venv as leftovers, which is exactly how `reportlab` reached production as a "
        "ModuleNotFoundError at import time:\n  " + "\n  ".join(missing)
    )


def test_reportlab_is_declared_specifically() -> None:
    """The regression, named, because this file is where someone will look."""
    assert "reportlab" in _declared(), (
        "reportlab renders the clinical brief PDF at runtime; without it the container "
        "cannot import app.main at all"
    )
