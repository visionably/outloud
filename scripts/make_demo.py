#!/usr/bin/env python3
"""Build examples/demo.pdf: one small report that carries a handful of real-world defects at once.

It is the file the README screenshots use and a quick thing to try outloud on:

    outloud examples/demo.pdf --view
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from tests.builder import Block, Fixture  # noqa: E402


def demo() -> Fixture:
    fx = Fixture(title="water_report_FINAL_v3.pdf")
    fx.h(1, "Annual water quality report")
    fx.p("This report describes the drinking water supplied to the town during the year.")
    fx.h(3, "How the samples were taken")
    fx.p("Samples were taken at the works and at six points in the network.")
    fx.figure(alt="IMG_2041.jpg", caption="Figure 1. The treatment works from the east bank")
    fx.table([["Month", "Samples", "Passed"], ["January", "24", "24"], ["February", "22", "21"], ["March", "26", "26"]], headers_ids=True, empty_th=True)
    fx.untagged("Fourth-quarter results were added later and nobody tagged them.")
    fx.artifact("Two February samples exceeded the turbidity limit; both passed on re-test.")
    fx.p("Questions: write to water@example.org or see https://example.org/water")
    fx.link("Read the full data", contents=None)
    fx.formula("c = m / V", alt="\\frac{m}{V}")
    return fx


if __name__ == "__main__":
    out = ROOT / "examples" / "demo.pdf"
    demo().build(str(out))
    print(f"wrote {out}")
