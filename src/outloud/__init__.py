"""outloud: a fast PDF accessibility checker for the terminal.

    from outloud import check
    result = check("report.pdf")
    print(result.verdict, result.errors, result.warnings)
    for row in result.criteria["wcag22"]:
        print(row["id"], row["name"], row["status"])
"""

from __future__ import annotations

import time
from typing import Optional

from .findings import Result
from .model import Document
from .registry import features, load_catalogue, run_rules

__version__ = "0.2.0"


def check(path: str, source: Optional[str] = None, only=None, skip=None, layers=None) -> Result:
    """Check one PDF and return a Result; never raises for a bad file."""
    from .criteria import evaluate  # noqa: PLC0415

    t0 = time.perf_counter()
    result = Result(path=path)
    doc = None
    try:
        doc = Document(path, source=source)
        pages = doc.pages
        result.stats["pages"] = len(pages)
        result.stats["tagged"] = bool(doc.struct_root is not None)
        feats = features(doc)
        result.stats["features"] = {k: v for k, v in feats.items() if v}
        run_rules(doc, result, only=set(only) if only else None, skip=set(skip) if skip else None,
                  layers=set(layers) if layers else None, feats=feats)
        result.stats["elements"] = len(doc.elements)
        result.stats["fonts"] = len(doc.fonts)
        result.criteria = evaluate(result, load_catalogue())
    except Exception as exc:  # noqa: BLE001
        result.error = f"{type(exc).__name__}: {exc}"[:300]
    finally:
        if doc is not None:
            doc.close()
    result.seconds = time.perf_counter() - t0
    return result
