#!/usr/bin/env python3
"""Run veraPDF and outloud over the same files and tabulate where they agree.

    python3 scripts/compare_verapdf.py DIR_OR_FILES... [--verapdf PATH] [--json out.json]

veraPDF is the reference validator for PDF/UA-1 syntax. For every file the
table shows veraPDF's verdict (compliant or not, with its failed rule count),
outloud's conformance-layer verdict, and outloud's semantic findings, which
veraPDF has no equivalent for. Timing is wall-clock per file for each tool.
A disagreement is not automatically a bug in either tool; the point of the
table is to make each one visible so it can be looked at.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from outloud import check  # noqa: E402
from outloud.registry import load_catalogue  # noqa: E402


def find_verapdf(explicit: str | None) -> str | None:
    for cand in [explicit, os.environ.get("VERAPDF_PATH"), shutil.which("verapdf")]:
        if cand and os.path.exists(cand):
            return cand
    return None


def run_verapdf(binary: str, path: str) -> dict:
    t0 = time.perf_counter()
    try:
        proc = subprocess.run([binary, "--flavour", "ua1", "--format", "json", path], capture_output=True, text=True, timeout=300)
        seconds = time.perf_counter() - t0
        data = json.loads(proc.stdout) if proc.stdout.strip().startswith("{") else {}
    except Exception as exc:  # noqa: BLE001
        return {"compliant": None, "failed": None, "seconds": time.perf_counter() - t0, "error": str(exc)[:120]}
    compliant, failed, rules = None, 0, []
    jobs = (data.get("report", {}).get("jobs") or []) if isinstance(data, dict) else []
    for job in jobs:
        vr = job.get("validationResult") or {}
        if isinstance(vr, list):
            vr = vr[0] if vr else {}
        if "compliant" in vr:
            compliant = bool(vr.get("compliant"))
        details = vr.get("details") or {}
        failed = int(details.get("failedRules", 0) or 0)
        for r in details.get("ruleSummaries") or []:
            if r.get("ruleStatus") == "FAILED":
                rules.append(f"{r.get('clause')}-{r.get('testNumber')}")
    return {"compliant": compliant, "failed": failed, "rules": rules, "seconds": seconds}


def expand(paths) -> list[str]:
    out = []
    for p in paths:
        if os.path.isdir(p):
            out += sorted(str(x) for x in Path(p).rglob("*.pdf"))
        else:
            out.append(p)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--verapdf")
    ap.add_argument("--json")
    args = ap.parse_args()
    binary = find_verapdf(args.verapdf)
    if binary is None:
        print("veraPDF not found: pass --verapdf PATH or set VERAPDF_PATH", file=sys.stderr)
        sys.exit(2)
    cat = load_catalogue()
    rows = []
    files = expand(args.paths)
    for path in files:
        v = run_verapdf(binary, path)
        r = check(path)
        conf_err = sum(f.count for f in r.findings if f.severity == "error" and cat[f.rule].layer == "conformance" and cat[f.rule].verapdf)
        extra_err = sum(f.count for f in r.findings if f.severity == "error" and cat[f.rule].layer == "conformance" and not cat[f.rule].verapdf)
        sem = [f for f in r.findings if cat[f.rule].layer == "semantic"]
        sem_err = sum(f.count for f in sem if f.severity == "error")
        sem_warn = sum(f.count for f in sem if f.severity == "warning")
        tc_conf = "compliant" if conf_err == 0 and r.error is None else "not compliant"
        vera = "compliant" if v.get("compliant") else ("not compliant" if v.get("compliant") is False else "error")
        rows.append({
            "file": os.path.basename(path), "pages": r.stats.get("pages"),
            "verapdf": vera, "verapdf_failed_rules": v.get("failed"), "verapdf_rules": v.get("rules", [])[:8], "verapdf_seconds": round(v["seconds"], 2),
            "outloud_conformance": tc_conf, "outloud_conformance_errors": conf_err, "outloud_extra_conformance_errors": extra_err,
            "outloud_semantic_errors": sem_err, "outloud_semantic_warnings": sem_warn,
            "outloud_rules": sorted({f.rule for f in r.findings}), "outloud_seconds": round(r.seconds, 2),
            "agree": vera == tc_conf,
        })
        print(f"{os.path.basename(path)[:44]:<44} vera={vera:<14} ({v.get('failed')}) {v['seconds']:5.1f}s | outloud={tc_conf:<14} conf-err={conf_err:<3} +{extra_err:<2} sem-err={sem_err:<3} sem-warn={sem_warn:<3} {r.seconds:5.2f}s | {'agree' if vera == tc_conf else 'DIFFER'}")
    n = len(rows)
    agree = sum(1 for x in rows if x["agree"])
    vt = sum(x["verapdf_seconds"] for x in rows)
    tt = sum(x["outloud_seconds"] for x in rows)
    print(f"\n{n} file(s): conformance verdict agrees on {agree} ({100 * agree / max(1, n):.0f}%); veraPDF {vt:.1f}s total, outloud {tt:.1f}s total ({vt / max(tt, 0.001):.0f}x)")
    sem_only = sum(1 for x in rows if x["verapdf"] == "compliant" and (x["outloud_semantic_errors"] or x["outloud_semantic_warnings"]))
    print(f"files veraPDF calls compliant where outloud's semantic layer still reports something: {sem_only}")
    extra = sum(1 for x in rows if x["outloud_extra_conformance_errors"])
    print(f"files where outloud's conformance rules that veraPDF lacks (verapdf: no) report an error: {extra}")
    if args.json:
        Path(args.json).write_text(json.dumps({"verapdf": binary, "rows": rows}, indent=2))


if __name__ == "__main__":
    main()
