"""CLI interface for BibSanity."""

import asyncio
from pathlib import Path
from typing import Optional
import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeRemainingColumn

from .core import Verifier
from .cache import Cache
from .utils import parse_bibtex
from .report import Reporter

app = typer.Typer(help="BibSanity - Sanity checks for BibTeX entries")
console = Console()


@app.command()
def check(
    file: Path = typer.Argument(..., help="Path to .bib file"),
    json: Optional[Path] = typer.Option(
        None, "--json", "-j", help="Path for JSON report (default: xxx_report.json)"
    ),
    out: Optional[Path] = typer.Option(
        None, "--out", "-o", help="Path for HTML report (deprecated, use --format instead)"
    ),
    format: Optional[str] = typer.Option(
        None, "--format", "-f", help="Output format: json, html, pdf, or all (default: json)"
    ),
    max_workers: int = typer.Option(
        6, "--max-workers", "-w", help="Maximum concurrent workers"
    ),
    strict: bool = typer.Option(
        False, "--strict", "-s", help="Use strict verification mode"
    ),
    no_cache: bool = typer.Option(
        False, "--no-cache", help="Disable caching"
    ),
):
    """Check BibTeX file for sanity issues."""
    # Validate input file
    file_path = Path(file)
    if not file_path.exists():
        console.print(f"[red]Error:[/red] File not found: {file_path}")
        raise typer.Exit(1)

    if not file_path.suffix.lower() == ".bib":
        console.print(f"[yellow]Warning:[/yellow] File does not have .bib extension: {file_path}")

    # Parse BibTeX file
    try:
        console.print(f"[cyan]Parsing BibTeX file:[/cyan] {file_path}")
        entries = parse_bibtex(str(file_path))
        console.print(f"[green]✓[/green] Found {len(entries)} entries")
    except Exception as e:
        console.print(f"[red]Error parsing BibTeX file:[/red] {e}")
        raise typer.Exit(1)

    if not entries:
        console.print("[yellow]Warning:[/yellow] No entries found in BibTeX file")
        raise typer.Exit(0)

    # Initialize verifier
    cache = Cache(enabled=not no_cache)
    verifier = Verifier(
        cache=cache,
        strict=strict,
        max_workers=max_workers,
    )

    # Verify entries with progress bar
    console.print("[cyan]Verifying entries...[/cyan]")
    try:
        # Create progress bar
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TextColumn("({task.completed}/{task.total})"),
            TimeRemainingColumn(),
            console=console,
            transient=False,
        ) as progress:
            task = progress.add_task(
                "[cyan]Verifying...", 
                total=len(entries)
            )
            
            def update_progress(completed: int, total: int, entry_id: str):
                """Update progress bar with current entry info."""
                # Rich Progress is thread-safe and can be updated from async context
                progress.update(
                    task,
                    completed=completed,
                    description=f"[cyan]Verifying...[/cyan] [dim]{entry_id}[/dim]"
                )
            
            # Run verification with progress callback
            async def verify_with_progress():
                return await verifier.verify_entries(entries, progress_callback=update_progress)
            
            results = asyncio.run(verify_with_progress())
            
            # Final update to show completion
            progress.update(task, completed=len(entries), description="[green]✓ Verification complete[/green]")
    except Exception as e:
        console.print(f"[red]Error during verification:[/red] {e}")
        raise typer.Exit(1)

    # Generate reports
    reporter = Reporter()

    # Terminal report
    reporter.print_terminal_report(results)

    # Determine base name from input file (without .bib extension)
    file_stem = file_path.stem  # e.g., "test_refs" from "test_refs.bib"
    file_dir = file_path.parent  # Directory of the input file
    
    # Create Sanity_Report folder in the same directory as input file
    report_dir = file_dir / "Sanity_Report"
    report_dir.mkdir(exist_ok=True)  # Create if doesn't exist, do nothing if exists

    # Determine output formats
    formats_to_generate = set()
    
    # Handle --format option
    if format:
        format_lower = format.lower()
        if format_lower == "all":
            formats_to_generate = {"json", "html"}
        elif format_lower in ("json", "html"):
            formats_to_generate = {format_lower}
        else:
            console.print(f"[red]Error:[/red] Invalid format '{format}'. Use: json, html, or all")
            raise typer.Exit(1)
    # Handle --out option (backward compatibility)
    elif out:
        out_path = Path(out)
        # If user provided just a filename without path, put it in report dir
        if not out_path.is_absolute() and out_path.parent == Path("."):
            out_path = report_dir / out_path.name
        
        # Determine format from extension
        ext = out_path.suffix.lower()
        if ext == ".html":
            formats_to_generate = {"html"}
            # Use custom path for HTML
            report_dir = out_path.parent
            file_stem = out_path.stem.replace("_report", "")  # Remove _report if present
        else:
            formats_to_generate = {"html"}  # Default to HTML for --out
    else:
        # Default: only JSON (backward compatible)
        formats_to_generate = {"json"}

    # Always generate JSON (default behavior, unless user explicitly uses --format without json)
    # If --format is used, only generate JSON if it's in the format list
    # Otherwise (default or --out), always generate JSON
    should_generate_json = (
        "json" in formats_to_generate 
        or (not format and not out)  # Default: no --format and no --out
        or (out and not format)      # --out without --format (backward compat)
    )
    
    if should_generate_json:
        if json:
            # User specified custom path
            json_path = Path(json)
        else:
            # Default: in Sanity_Report folder, with _report.json suffix
            json_path = report_dir / f"{file_stem}_report.json"
        reporter.save_json_report(results, str(json_path))

    # Generate HTML report
    if "html" in formats_to_generate:
        html_path = report_dir / f"{file_stem}_report.html"
        reporter.save_html_report(results, str(html_path))

    # Exit code based on results
    has_failures = any(r.status == "FAIL" for r in results)
    if has_failures:
        raise typer.Exit(1)
    else:
        raise typer.Exit(0)


if __name__ == "__main__":
    app()
