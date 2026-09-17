#!/usr/bin/env python3
"""Run pdfa11y (speedata's Go checker) and outloud over the same files and tabulate where they differ.

    python3 scripts/compare_pdfa11y.py DIR_OR_FILES... --pdfa11y /path/to/pdfa11y [--json out.json]

pdfa11y has no semantic layer, so the comparison is on conformance verdicts:
its PASS/WARN/FAIL against outloud's conformance-layer errors. Each
disagreement is listed with the checks that caused it, so a reader can decide
who is right (build a fixture, or read the spec clause both cite).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from outloud import check  # noqa: E402
from outloud.findings import ERROR  # noqa: E402
from outloud.registry import load_catalogue  # noqa: E402


def expand(paths: list[str]) -> list[str]:
    out = []
    for p in paths:
        if os.path.isdir(p):
            out.extend(sorted(str(x) for x in Path(p).glob("*.pdf")))
        else:
            out.append(p)
    return out


def run_pdfa11y(binary: str, files: list[str]) -> tuple[dict[str, dict], float]:
    t0 = time.perf_counter()
    proc = subprocess.run([binary, "--format", "json", "--spec", "pdfua1", *files], capture_output=True, text=True, timeout=600)
    seconds = time.perf_counter() - t0
    try:
        docs = json.loads(proc.stdout)
    except json.JSONDecodeError:
        sys.exit(f"pdfa11y produced no JSON: {proc.stderr[:300]}")
    return {os.path.abspath(d["path"]): d for d in docs}, seconds


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--pdfa11y", required=True, help="path to the pdfa11y binary")
    ap.add_argument("--json", dest="json_out")
    args = ap.parse_args()
    files = expand(args.paths)
    if not files:
        sys.exit("no PDF files")
    theirs, their_seconds = run_pdfa11y(args.pdfa11y, files)
    cat = load_catalogue()
    rows = []
    our_seconds = 0.0
    for path in files:
        r = check(path)
        our_seconds += r.seconds
        conf_errors = sorted({f.rule for f in r.findings if f.severity == ERROR and cat[f.rule].layer == "conformance"})
        d = theirs.get(os.path.abspath(path), {})
        their_fail = sorted(x["id"] for x in d.get("results", []) if x.get("state") == "FAIL")
        their_verdict = d.get("verdict", "?")
        ours = "FAIL" if conf_errors else "PASS"
        agree = (their_verdict == "FAIL") == (ours == "FAIL")
        rows.append({"file": os.path.basename(path), "pdfa11y": their_verdict, "pdfa11y_failed": their_fail,
                     "outloud": ours, "outloud_conformance_errors": conf_errors, "agree": agree,
                     "outloud_semantic": sorted({f.rule for f in r.findings if cat[f.rule].layer == "semantic"})})
    width = max(len(x["file"]) for x in rows)
    for x in rows:
        mark = "agree" if x["agree"] else "DIFFER"
        print(f"{x['file'][:width]:<{width}} pdfa11y={x['pdfa11y']:<5} {','.join(x['pdfa11y_failed'])[:48]:<48} | outloud={x['outloud']:<5} {','.join(x['outloud_conformance_errors'])[:40]:<40} | {mark}")
    n = len(rows)
    agree = sum(1 for x in rows if x["agree"])
    print(f"\n{n} file(s): conformance verdict agrees on {agree} ({100 * agree // max(1, n)}%); pdfa11y {their_seconds:.1f}s total (one process), outloud {our_seconds:.1f}s total")
    if args.json_out:
        Path(args.json_out).write_text(json.dumps({"pdfa11y_seconds": their_seconds, "outloud_seconds": our_seconds, "rows": rows}, indent=2))


if __name__ == "__main__":
    main()
