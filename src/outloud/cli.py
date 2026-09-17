"""The outloud command.

    outloud report.pdf                  one file, findings on the terminal
    outloud a.pdf b.pdf dir/            several; directories are searched for *.pdf
    outloud out.pdf --source in.pdf     also compare the output with its source
    outloud *.pdf --json report.json --sarif report.sarif --html report.html
    outloud --list-rules

Exit status: 0 when every file passes or needs review, 1 when any file
fails, 2 when any file could not be read. --fail-on changes the threshold.
"""

from __future__ import annotations

import os
import sys

import click

from . import __version__, check
from .findings import Result
from .report import batch_table, criteria_table, one_line, rules_table, terminal, to_html, to_json, to_sarif


def _expand(paths: tuple[str, ...]) -> list[str]:
    out: list[str] = []
    for p in paths:
        if os.path.isdir(p):
            for root, _dirs, files in os.walk(p):
                for f in sorted(files):
                    if f.lower().endswith(".pdf"):
                        out.append(os.path.join(root, f))
        else:
            out.append(p)
    return out


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.argument("paths", nargs=-1, type=click.Path())
@click.option("--source", type=click.Path(exists=True), help="The original PDF the checked file was made from; enables the SEM-* comparisons.")
@click.option("--json", "json_path", type=click.Path(), help="Write a JSON report to this path ('-' for stdout).")
@click.option("--sarif", "sarif_path", type=click.Path(), help="Write a SARIF 2.1.0 report to this path.")
@click.option("--html", "html_path", type=click.Path(), help="Write an HTML report to this path.")
@click.option("--only", multiple=True, help="Run only these rule ids (repeatable, or comma-separated).")
@click.option("--skip", multiple=True, help="Skip these rule ids (repeatable, or comma-separated).")
@click.option("--layer", type=click.Choice(["conformance", "semantic"]), multiple=True, help="Run only rules of this layer.")
@click.option("--fail-on", type=click.Choice(["error", "warning", "never"]), default="error", show_default=True,
              help="Which severity makes the exit status non-zero.")
@click.option("-q", "--quiet", is_flag=True, help="One line per file, no findings.")
@click.option("--no-info", is_flag=True, help="Hide info-level findings on the terminal.")
@click.option("--criteria", is_flag=True,
              help="Print the criteria view: every Matterhorn checkpoint and WCAG 2.2 A/AA success criterion with its status (pass, fail, warning, not applicable, needs a person) and the rules behind it.")
@click.option("--view", is_flag=True, help="Open the result in the browser: pages with findings outlined, the structure tree, and a screen-reader preview. One file at a time.")
@click.option("--port", type=int, default=0, help="Port for --view (default: any free port).")
@click.option("--no-browser", is_flag=True, help="With --view: serve without opening a browser window; print the URL instead.")
@click.option("--list-rules", is_flag=True, help="Print the rule catalogue and exit.")
@click.version_option(__version__, prog_name="outloud")
def main(paths, source, json_path, sarif_path, html_path, only, skip, layer, fail_on, quiet, no_info, criteria, view, port, no_browser, list_rules):
    """Check PDF files for accessibility: PDF/UA-1 conformance plus semantic checks a validator cannot make."""
    if list_rules:
        click.echo(rules_table())
        return
    files = _expand(paths)
    if not files:
        raise click.UsageError("give at least one PDF file or directory, or --list-rules")
    only_ids = {x.strip() for item in only for x in item.split(",") if x.strip()} or None
    skip_ids = {x.strip() for item in skip for x in item.split(",") if x.strip()} or None
    results: list[Result] = []
    for path in files:
        if not os.path.exists(path):
            r = Result(path=path, error="no such file")
        else:
            r = check(path, source=source, only=only_ids, skip=skip_ids, layers=set(layer) or None)
        results.append(r)
        if json_path == "-":
            continue
        if quiet or len(files) > 1:
            click.echo(one_line(r))
        else:
            click.echo(terminal(r, verbose=True, show_info=not no_info))
        if criteria and not r.error:
            if len(files) > 1:
                click.echo(f"  {os.path.basename(r.path)}")
            click.echo(criteria_table(r, "both"))
            click.echo("")
    if len(files) > 1 and json_path != "-" and not quiet:
        click.echo("")
        click.echo(batch_table(results))
    if json_path:
        text = to_json(results)
        if json_path == "-":
            click.echo(text)
        else:
            with open(json_path, "w", encoding="utf-8") as fh:
                fh.write(text)
    if sarif_path:
        with open(sarif_path, "w", encoding="utf-8") as fh:
            fh.write(to_sarif(results))
    if html_path:
        with open(html_path, "w", encoding="utf-8") as fh:
            fh.write(to_html(results))
    if view:
        if len(files) != 1:
            raise click.UsageError("--view takes exactly one file")
        if results[0].error:
            raise click.UsageError(f"cannot view: {results[0].error}")
        from .model import Document  # noqa: PLC0415
        from .viewer import serve  # noqa: PLC0415

        doc = Document(files[0], source=source)
        click.echo("viewer running; press Ctrl+C to stop", err=True)
        try:
            serve(results[0], doc, port=port, open_browser=not no_browser)
        finally:
            doc.close()
    code = 0
    if any(r.error for r in results):
        code = 2
    elif fail_on == "error" and any(r.errors for r in results):
        code = 1
    elif fail_on == "warning" and any(r.errors or r.warnings for r in results):
        code = 1
    sys.exit(code)


if __name__ == "__main__":
    main()
