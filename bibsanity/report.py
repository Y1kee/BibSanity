"""Reporting utilities for terminal, JSON, and HTML output."""

import json
from pathlib import Path
from typing import List, Dict, Any
from rich.console import Console
from rich.table import Table
from rich import box
from .core import VerificationResult


class Reporter:
    """Generate reports in various formats."""

    def __init__(self):
        """Initialize reporter."""
        self.console = Console()

    def print_terminal_report(self, results: List[VerificationResult]) -> None:
        """Print terminal report using Rich.

        Args:
            results: List of verification results
        """
        table = Table(title="BibSanity Verification Report", box=box.ROUNDED)
        table.add_column("Entry ID", style="cyan", no_wrap=True)
        table.add_column("Status", justify="center")
        table.add_column("Confidence", justify="right", style="magenta")
        table.add_column("Reason", style="white")

        status_colors = {
            "OK": "green",
            "WARN": "yellow",
            "FAIL": "red",
            "SKIP": "blue",
        }

        for result in results:
            status_style = status_colors.get(result.status, "white")
            # Format confidence as percentage
            if result.status == "SKIP":
                confidence_str = "N/A"
            else:
                confidence_pct = result.confidence * 100
                confidence_str = f"{confidence_pct:.0f}%"
            table.add_row(
                result.entry_id,
                f"[{status_style}]{result.status}[/{status_style}]",
                confidence_str,
                result.reason,
            )

        self.console.print(table)

        # Summary
        summary = {
            "OK": sum(1 for r in results if r.status == "OK"),
            "WARN": sum(1 for r in results if r.status == "WARN"),
            "FAIL": sum(1 for r in results if r.status == "FAIL"),
            "SKIP": sum(1 for r in results if r.status == "SKIP"),
        }

        self.console.print("\n[bold]Summary:[/bold]")
        self.console.print(f"  [green]OK:[/green] {summary['OK']}")
        self.console.print(f"  [yellow]WARN:[/yellow] {summary['WARN']}")
        self.console.print(f"  [red]FAIL:[/red] {summary['FAIL']}")
        if summary['SKIP'] > 0:
            self.console.print(f"  [blue]SKIP:[/blue] {summary['SKIP']}")

    def save_json_report(
        self, results: List[VerificationResult], file_path: str
    ) -> None:
        """Save JSON report.

        Args:
            results: List of verification results
            file_path: Output file path
        """
        report_data = {
            "summary": {
                "total": len(results),
                "ok": sum(1 for r in results if r.status == "OK"),
                "warn": sum(1 for r in results if r.status == "WARN"),
                "fail": sum(1 for r in results if r.status == "FAIL"),
                "skip": sum(1 for r in results if r.status == "SKIP"),
            },
            "results": [
                {
                    "entry_id": r.entry_id,
                    "status": r.status,
                    "reason": r.reason,
                    "confidence": r.confidence,
                    "confidence_percentage": r.confidence * 100 if r.status != "SKIP" else None,
                    "details": r.details,
                }
                for r in results
            ],
        }

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)

        self.console.print(f"\n[green]✓[/green] JSON report saved to: {file_path}")

    def _generate_html_content(self, results: List[VerificationResult]) -> str:
        """Generate HTML content for report.

        Args:
            results: List of verification results

        Returns:
            HTML content as string
        """
        summary = {
            "total": len(results),
            "ok": sum(1 for r in results if r.status == "OK"),
            "warn": sum(1 for r in results if r.status == "WARN"),
            "fail": sum(1 for r in results if r.status == "FAIL"),
            "skip": sum(1 for r in results if r.status == "SKIP"),
        }

        status_colors = {
            "OK": "#28a745",
            "WARN": "#ffc107",
            "FAIL": "#dc3545",
            "SKIP": "#17a2b8",
        }

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>BibSanity Verification Report</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        h1 {{
            color: #333;
            border-bottom: 3px solid #007bff;
            padding-bottom: 10px;
        }}
        .summary {{
            display: flex;
            gap: 20px;
            margin: 20px 0;
            flex-wrap: wrap;
        }}
        .summary-card {{
            background: white;
            padding: 15px 25px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            flex: 1;
            min-width: 150px;
        }}
        .summary-card h3 {{
            margin: 0 0 10px 0;
            font-size: 14px;
            color: #666;
            text-transform: uppercase;
        }}
        .summary-card .value {{
            font-size: 32px;
            font-weight: bold;
        }}
        .summary-card.ok .value {{ color: #28a745; }}
        .summary-card.warn .value {{ color: #ffc107; }}
        .summary-card.fail .value {{ color: #dc3545; }}
        .summary-card.skip .value {{ color: #17a2b8; }}
        .summary-card.total .value {{ color: #007bff; }}
        table {{
            width: 100%;
            border-collapse: collapse;
            background: white;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            border-radius: 8px;
            overflow: hidden;
        }}
        th {{
            background-color: #007bff;
            color: white;
            padding: 12px;
            text-align: left;
            font-weight: 600;
        }}
        td {{
            padding: 12px;
            border-bottom: 1px solid #eee;
        }}
        tr:hover {{
            background-color: #f8f9fa;
        }}
        .status {{
            display: inline-block;
            padding: 4px 12px;
            border-radius: 12px;
            font-weight: 600;
            font-size: 12px;
            text-transform: uppercase;
        }}
        .status.ok {{
            background-color: #d4edda;
            color: #155724;
        }}
        .status.warn {{
            background-color: #fff3cd;
            color: #856404;
        }}
        .status.fail {{
            background-color: #f8d7da;
            color: #721c24;
        }}
        .status.skip {{
            background-color: #d1ecf1;
            color: #0c5460;
        }}
        .reason {{
            color: #555;
        }}
        .details {{
            font-size: 12px;
            color: #888;
            margin-top: 4px;
        }}
    </style>
</head>
<body>
    <h1>BibSanity Verification Report</h1>
    
    <div class="summary">
        <div class="summary-card total">
            <h3>Total</h3>
            <div class="value">{summary['total']}</div>
        </div>
        <div class="summary-card ok">
            <h3>OK</h3>
            <div class="value">{summary['ok']}</div>
        </div>
        <div class="summary-card warn">
            <h3>Warn</h3>
            <div class="value">{summary['warn']}</div>
        </div>
        <div class="summary-card fail">
            <h3>Fail</h3>
            <div class="value">{summary['fail']}</div>
        </div>
"""
        if summary['skip'] > 0:
            html += f"""
        <div class="summary-card skip">
            <h3>Skip</h3>
            <div class="value">{summary['skip']}</div>
        </div>
"""
        html += """
    </div>

    <table>
        <thead>
            <tr>
                <th>Entry ID</th>
                <th>Status</th>
                <th>Confidence</th>
                <th>Reason</th>
            </tr>
        </thead>
        <tbody>
"""

        for result in results:
            status_class = result.status.lower()
            details_html = ""
            if result.details:
                details_items = []
                for key, value in result.details.items():
                    if key != "issues":
                        details_items.append(f"{key}: {value}")
                if details_items:
                    details_html = f'<div class="details">{", ".join(details_items)}</div>'

            # Format confidence
            if result.status == "SKIP":
                confidence_html = "<span style='color: #888;'>N/A</span>"
            else:
                confidence_pct = result.confidence * 100
                # Color code confidence: green for high, yellow for medium, red for low
                if confidence_pct >= 90:
                    conf_color = "#28a745"
                elif confidence_pct >= 70:
                    conf_color = "#ffc107"
                else:
                    conf_color = "#dc3545"
                confidence_html = f"<span style='color: {conf_color}; font-weight: 600;'>{confidence_pct:.0f}%</span>"

            html += f"""
            <tr>
                <td><strong>{result.entry_id}</strong></td>
                <td><span class="status {status_class}">{result.status}</span></td>
                <td>{confidence_html}</td>
                <td>
                    <div class="reason">{result.reason}</div>
                    {details_html}
                </td>
            </tr>
"""

        html += """
        </tbody>
    </table>
</body>
</html>
"""
        return html

    def save_html_report(
        self, results: List[VerificationResult], file_path: str
    ) -> None:
        """Save HTML report.

        Args:
            results: List of verification results
            file_path: Output file path
        """
        html = self._generate_html_content(results)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(html)
        self.console.print(f"[green]✓[/green] HTML report saved to: {file_path}")

