"""The command itself, run as a user's shell runs it."""

from __future__ import annotations

import os
import subprocess
import sys

from .builder import clean


def test_report_survives_a_non_utf8_stdout(tmp_path):
    # Ligatures and a minus sign are not in cp1252; TAG-001 quotes the untagged run as evidence.
    pdf = str(tmp_path / "ligature.pdf")
    clean().untagged("The ﬁrst oﬃce ﬁle, −2 degrees").build(pdf)
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONUTF8", "PYTHONIOENCODING")}
    env["PYTHONIOENCODING"] = "cp1252"
    for args in ([pdf], [pdf, "--json", "-"]):
        p = subprocess.run([sys.executable, "-c", "from outloud.cli import main; main()", *args, "--fail-on", "never"],
                           capture_output=True, env=env)
        assert p.returncode == 0, p.stderr.decode("utf-8", "replace")
        assert "TAG-001" in p.stdout.decode("utf-8")
