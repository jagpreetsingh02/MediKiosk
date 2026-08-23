"""Reference ranges and out-of-range flagging.

The rule that matters: **a range printed on the report always wins.** Labs differ, methods
differ, and a value flagged "high" against our table when the patient's own report says it is
normal destroys the physician's trust in every other flag on the screen. Our table is the
fallback for when the report prints no range at all.

And the flag is a *range comparison*, never an interpretation. `range_flag: "high"` means the
number exceeds the interval; it does not mean anything is wrong with the patient. That
distinction is Invariant 1 at the level of a single field.
"""

from __future__ import annotations

import functools
import json
import re
from dataclasses import dataclass
from typing import Literal

from app.core.config import settings

RangeFlag = Literal["low", "high", "in_range", "unknown"]


@dataclass(frozen=True, slots=True)
class Analyte:
    key: str
    display: str
    unit: str
    aliases: tuple[str, ...]
    ranges: tuple[dict, ...]

    def interval(self, sex: str | None) -> tuple[float, float] | None:
        for entry in self.ranges:
            if "sex" not in entry:
                return float(entry["low"]), float(entry["high"])
        for entry in self.ranges:
            if entry.get("sex") == (sex or "").casefold():
                return float(entry["low"]), float(entry["high"])
        if self.ranges:
            entry = self.ranges[0]
            return float(entry["low"]), float(entry["high"])
        return None


@functools.lru_cache(maxsize=1)
def load_analytes() -> tuple[Analyte, ...]:
    path = settings.path(settings.terminology_seed_dir) / "reference-ranges.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    return tuple(
        Analyte(
            key=item["key"],
            display=item["display"],
            unit=item["unit"],
            aliases=tuple(a.casefold() for a in item["aliases"]),
            ranges=tuple(item["ranges"]),
        )
        for item in payload["analytes"]
    )


_NON_WORD = re.compile(r"[^a-z0-9]+")


def _fold(text: str) -> str:
    return _NON_WORD.sub(" ", text.casefold()).strip()


def match_analyte(label: str) -> Analyte | None:
    """Longest alias wins, so 'total cholesterol' does not match the alias 'cholesterol'."""
    folded = _fold(label)
    if not folded:
        return None
    best: tuple[int, Analyte] | None = None
    for analyte in load_analytes():
        for alias in analyte.aliases:
            if alias == folded or f" {alias} " in f" {folded} ":
                if best is None or len(alias) > best[0]:
                    best = (len(alias), analyte)
    return best[1] if best else None


#: "4.0 - 5.6", "4.0-5.6", "< 200", "up to 150", "0.4 to 4.0"
_PRINTED_RANGE = re.compile(
    r"(?:(?P<low>\d+(?:\.\d+)?)\s*(?:-|–|to)\s*(?P<high>\d+(?:\.\d+)?))"
    r"|(?:(?:<|less than|up ?to|upto)\s*(?P<max>\d+(?:\.\d+)?))"
    r"|(?:(?:>|greater than|above)\s*(?P<min>\d+(?:\.\d+)?))",
    re.IGNORECASE,
)


def parse_printed_range(text: str) -> tuple[float | None, float | None] | None:
    """Pull an interval out of the report's own text. Wins over the fallback table."""
    match = _PRINTED_RANGE.search(text)
    if match is None:
        return None
    if match.group("low") is not None:
        return float(match.group("low")), float(match.group("high"))
    if match.group("max") is not None:
        return None, float(match.group("max"))
    if match.group("min") is not None:
        return float(match.group("min")), None
    return None


@dataclass(frozen=True, slots=True)
class RangeAssessment:
    flag: RangeFlag
    low: float | None
    high: float | None
    unit: str | None
    analyte_key: str | None
    display: str | None
    #: Where the interval came from. Surfaced to the physician verbatim.
    source: Literal["report", "reference_table", "none"]


def assess(
    label: str,
    value: float | None,
    *,
    printed_range: str | None = None,
    sex: str | None = None,
) -> RangeAssessment:
    """Compare a value to its interval. Returns `unknown` freely — that is a valid answer."""
    analyte = match_analyte(label)

    interval: tuple[float | None, float | None] | None = None
    source: Literal["report", "reference_table", "none"] = "none"

    if printed_range:
        interval = parse_printed_range(printed_range)
        if interval is not None:
            source = "report"
    if interval is None and analyte is not None:
        table = analyte.interval(sex)
        if table is not None:
            interval = table
            source = "reference_table"

    if value is None or interval is None:
        return RangeAssessment(
            flag="unknown",
            low=None,
            high=None,
            unit=analyte.unit if analyte else None,
            analyte_key=analyte.key if analyte else None,
            display=analyte.display if analyte else None,
            source=source,
        )

    low, high = interval
    if low is not None and value < low:
        flag: RangeFlag = "low"
    elif high is not None and value > high:
        flag = "high"
    else:
        flag = "in_range"

    return RangeAssessment(
        flag=flag,
        low=low,
        high=high,
        unit=analyte.unit if analyte else None,
        analyte_key=analyte.key if analyte else None,
        display=analyte.display if analyte else None,
        source=source,
    )
