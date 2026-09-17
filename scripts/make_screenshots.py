#!/usr/bin/env python3
"""Regenerate the README screenshots in docs/img/ with headless Chrome.

    python3 scripts/make_screenshots.py [--real /path/to/a/real.pdf]

Serves the app on a local port, opens exact states through its deep links
(?doc=&tab=&fw=&f=), and photographs them. The terminal picture is the real
CLI output, set in a small HTML page. Needs Google Chrome or Chromium.
"""

from __future__ import annotations

import argparse
import html
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from outloud import check  # noqa: E402
from outloud.model import Document  # noqa: E402
from outloud.report import criteria_table, terminal  # noqa: E402
from outloud.viewer import serve  # noqa: E402

CHROME = [p for p in ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "/Applications/Chromium.app/Contents/MacOS/Chromium",
                      "/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser") if os.path.exists(p)]
IMG = ROOT / "docs" / "img"


def shoot(url: str, out: Path, size=(1440, 900), budget=7000) -> None:
    subprocess.run([CHROME[0], "--headless=new", f"--screenshot={out}", f"--window-size={size[0]},{size[1]}", "--force-device-scale-factor=2",
                    "--hide-scrollbars", f"--virtual-time-budget={budget}", "--no-first-run", "--disable-gpu", url],
                   check=True, capture_output=True, timeout=120)
    print(f"  {out.relative_to(ROOT)}  {out.stat().st_size // 1024} KB")


TERM_CSS = """body{margin:0;background:#16161a;display:flex;justify-content:center;padding:36px}
.win{width:1180px;background:#1e1e24;border-radius:10px;box-shadow:0 20px 60px rgba(0,0,0,.5);overflow:hidden;font:14.5px/1.55 ui-monospace,SFMono-Regular,Menlo,monospace;color:#d6d3cd}
.bar{height:34px;background:#2a2a32;display:flex;align-items:center;gap:8px;padding:0 14px}.bar i{width:12px;height:12px;border-radius:50%;display:block}
.bar i:nth-child(1){background:#ff5f57}.bar i:nth-child(2){background:#febc2e}.bar i:nth-child(3){background:#28c840}.bar span{margin-left:12px;color:#8d8a84;font-size:12.5px}
pre{margin:0;padding:20px 24px 26px;white-space:pre-wrap}.p{color:#8d8a84}.c{color:#f5f2ed}.e{color:#ff6b6b;font-weight:700}.w{color:#f0b429;font-weight:700}.ok{color:#4cc38a;font-weight:700}
.r{color:#7cc4ff}.m{color:#8d8a84}.fx{color:#9fe0b8}.na{color:#8d8a84}.pe{color:#7cc4ff;font-weight:700}"""


def colour(text: str) -> str:
    out = []
    for line in text.splitlines():
        h = html.escape(line)
        h = re.sub(r"^(FAIL)\b", r"<span class='e'>\1</span>", h)
        h = re.sub(r"^(REVIEW)\b", r"<span class='w'>\1</span>", h)
        h = re.sub(r"^(PASS)\b", r"<span class='ok'>\1</span>", h)
        h = re.sub(r"^(\s+)(ERROR)(\s+)([A-Z]+-\d+)", r"\1<span class='e'>\2</span>\3<span class='r'>\4</span>", h)
        h = re.sub(r"^(\s+)(WARNING)(\s+)([A-Z]+-\d+)", r"\1<span class='w'>\2</span>\3<span class='r'>\4</span>", h)
        h = re.sub(r"^(\s+)(FAIL)(\s)", r"\1<span class='e'>\2</span>\3", h)
        h = re.sub(r"^(\s+)(WARN)(\s)", r"\1<span class='w'>\2</span>\3", h)
        h = re.sub(r"^(\s+)(PASS)(\s)", r"\1<span class='ok'>\2</span>\3", h)
        h = re.sub(r"^(\s+)(N/A)(\s)", r"\1<span class='na'>\2</span>\3", h)
        h = re.sub(r"^(\s+)(PERSON)(\s)", r"\1<span class='pe'>\2</span>\3", h)
        if re.match(r"^\s+fix:", line):
            h = f"<span class='fx'>{h}</span>"
        elif re.match(r"^\s+(evidence:|[A-Z][a-z].* — )", line):
            h = f"<span class='m'>{h}</span>"
        out.append(h)
    return "\n".join(out)


def term_page(command: str, body: str, path: Path) -> None:
    page = (f"<!doctype html><meta charset='utf-8'><style>{TERM_CSS}</style><div class='win'><div class='bar'><i></i><i></i><i></i><span>zsh</span></div>"
            f"<pre><span class='p'>$</span> <span class='c'>{html.escape(command)}</span>\n{colour(body)}</pre></div>")
    path.write_text(page, encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--real", help="a real-world PDF for the 'a validator passes this' picture")
    args = ap.parse_args()
    if not CHROME:
        sys.exit("Chrome or Chromium not found")
    IMG.mkdir(parents=True, exist_ok=True)
    demo = str(ROOT / "examples" / "demo.pdf")
    paths = [p for p in (args.real, demo) if p]
    results = [check(p) for p in paths]
    docs = [Document(p) for p in paths]
    url, httpd, store = serve(results, docs, open_browser=False, block=False)
    url2, httpd2, store2 = serve([], [], open_browser=False, block=False)
    tmp = Path(tempfile.mkdtemp(prefix="outloud-shots-"))
    try:
        print("screenshots:")
        shoot(url + "?doc=demo&eager=1&f=TBL-011", IMG / "app-findings.png")
        shoot(url + "?doc=demo&eager=1&tab=crit&fw=wcag22", IMG / "app-criteria.png")
        shoot(url + "?doc=demo&eager=1&tab=tree", IMG / "app-structure.png")
        shoot(url2, IMG / "app-drop.png", size=(1440, 760))
        if args.real:
            name = os.path.basename(args.real)[:12]
            shoot(url + f"?doc={name}&eager=1&f=TBL-011", IMG / "app-real.png", budget=20000)
        r = results[-1]
        body = terminal(r, verbose=True, show_info=False)
        keep = body.splitlines()
        term_page("outloud examples/demo.pdf", "\n".join(keep[:22] + ["  …"] + keep[-2:]), tmp / "t1.html")
        shoot((tmp / "t1.html").as_uri(), IMG / "terminal.png", size=(1252, 760), budget=1500)
        crit = criteria_table(r, "wcag22").splitlines()
        rows = [ln for ln in crit if not re.match(r"^\s+N/A", ln)][:20]
        term_page("outloud examples/demo.pdf --criteria", "\n".join(rows + ["  …"]), tmp / "t2.html")
        shoot((tmp / "t2.html").as_uri(), IMG / "terminal-criteria.png", size=(1252, 640), budget=1500)
    finally:
        for h in (httpd, httpd2):
            h.shutdown(); h.server_close()
        store.close(); store2.close()


if __name__ == "__main__":
    main()
