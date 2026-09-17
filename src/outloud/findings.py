"""Findings and results: the only things a rule produces and the CLI consumes."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Optional

ERROR, WARNING, INFO = "error", "warning", "info"
SEVERITY_ORDER = {ERROR: 0, WARNING: 1, INFO: 2}


@dataclass
class Finding:
    """One defect, at one place, with the evidence that shows it.

    `page` is 1-based, as people count pages, and None for document-level
    findings. `location` names where on the page (a structure element path,
    a marked-content id, a bounding box); `evidence` is the text or value the
    rule saw. `count` lets a rule fold many identical hits into one line
    ("47 links without /Contents") while keeping the first as the sample.
    """

    rule: str
    severity: str
    message: str
    page: Optional[int] = None
    location: dict = field(default_factory=dict)
    evidence: Optional[str] = None
    count: int = 1
    boxes: list = field(default_factory=list)   # [{page, x0, y0, x1, y1}] in PDF user space, for highlighting

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if not d["location"]:
            d.pop("location")
        if not d["boxes"]:
            d.pop("boxes")
        if d["evidence"] is None:
            d.pop("evidence")
        if d["page"] is None:
            d.pop("page")
        return d


@dataclass
class RuleRun:
    """What happened to one rule during a check: ran, skipped, or crashed."""

    rule: str
    status: str            # "ran" | "skipped" | "not-implemented" | "not-applicable" | "crashed"
    reason: Optional[str] = None
    findings: int = 0
    seconds: float = 0.0
    outcome: str = "not-run"   # "pass" | "fail" | "warning" | "info" | "not-applicable" | "not-run"


@dataclass
class Result:
    path: str
    findings: list[Finding] = field(default_factory=list)
    runs: list[RuleRun] = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    seconds: float = 0.0
    error: Optional[str] = None
    criteria: dict = field(default_factory=dict)   # {"pdfua1": [...], "wcag22": [...]} from criteria.evaluate

    @property
    def errors(self) -> int:
        return sum(f.count for f in self.findings if f.severity == ERROR)

    @property
    def warnings(self) -> int:
        return sum(f.count for f in self.findings if f.severity == WARNING)

    @property
    def infos(self) -> int:
        return sum(f.count for f in self.findings if f.severity == INFO)

    @property
    def verdict(self) -> str:
        """pass | review | fail | unreadable.

        fail = at least one error; review = warnings only; pass = nothing at
        error or warning level. "unreadable" means the file could not be
        opened, which is a result too, not an absence of one.
        """
        if self.error:
            return "unreadable"
        if self.errors:
            return "fail"
        if self.warnings:
            return "review"
        return "pass"

    def sorted_findings(self) -> list[Finding]:
        return sorted(self.findings, key=lambda f: (SEVERITY_ORDER.get(f.severity, 9), f.page or 0, f.rule))

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "verdict": self.verdict,
            "counts": {"error": self.errors, "warning": self.warnings, "info": self.infos},
            "seconds": round(self.seconds, 3),
            "error": self.error,
            "stats": self.stats,
            "findings": [f.to_dict() for f in self.sorted_findings()],
            "rules": [asdict(r) for r in self.runs],
            "criteria": self.criteria,
        }
