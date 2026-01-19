# BibSanity

Experimental note: This project started as a one-day, vibe-coded experiment. Expect rough edges.

A CLI tool to sanity-check BibTeX entries and flag likely invalid citations or inconsistent metadata.

## Features

- **Hybrid Verification Logic**: DOI lookup via Crossref API, falling back to title search via OpenAlex API
- **Multiple Report Formats**: Terminal output (Rich tables), JSON, and HTML reports
- **Organized Output**: Reports are saved in `Sanity_Report` next to the input file
- **Caching**: Caches API responses to reduce redundant requests
- **Concurrent Processing**: Verifies multiple entries in parallel
- **Conservative Language**: Uses FAIL/WARN/OK statuses with clear reasons

## Installation

From PyPI:

```bash
pip install bibsanity
```

From source:

```bash
git clone https://github.com/<your-username>/<repo>.git
cd BibSanity
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Quickstart

```bash
bibsanity examples/test_refs.bib
```

### Options

- `--format, -f FORMAT`: Output format: `json`, `html`, or `all` (default: `json`)
- `--json, -j PATH`: Custom path for JSON report (default: saved in `Sanity_Report`)
- `--out, -o PATH`: Custom path for HTML report (deprecated; use `--format` instead)
- `--max-workers, -w N`: Maximum concurrent workers (default: 6)
- `--strict, -s`: Use strict verification mode (treats warnings as failures)
- `--no-cache`: Disable caching

### Examples

```bash
# Basic check (generates JSON report in Sanity_Report folder)
bibsanity examples/test_refs.bib

# Generate HTML report
bibsanity references.bib --format html

# Generate all formats (JSON + HTML)
bibsanity references.bib --format all

# Custom JSON report path
bibsanity references.bib --json custom_report.json

# Strict mode with more workers
bibsanity references.bib --strict --max-workers 10
```

### Report Location

Reports are automatically saved in a `Sanity_Report` folder next to your input file:

```
references.bib
Sanity_Report/
  ├── references_report.json
  └── references_report.html
```

## Verification Logic

1. **DOI-based verification** (if DOI is present):
   - Looks up the DOI in Crossref API
   - Compares title, year, and authors
   - Returns OK if metadata matches, WARN/FAIL if inconsistencies found

2. **Title-based verification** (if no DOI or DOI lookup fails):
   - Searches OpenAlex API by title
   - Uses fuzzy matching to find best match
   - Compares year and authors
   - Returns OK if good match found, WARN/FAIL if inconsistencies found

3. **Failure cases**:
   - No DOI and no title match found
   - Metadata inconsistencies (year, authors, title mismatch)

## Known Limitations / Possible False Positives

1. Old papers published in conferences and journals with highly similar titles.
2. Titles with special characters such as `$$` or LaTeX equations.
3. Non-English papers or journals that are not indexed in Crossref or OpenAlex.

## Report Formats

### Terminal Report
Rich-formatted table showing entry ID, status, and reason.

### JSON Report
Structured JSON with summary statistics and detailed results for each entry.

### HTML Report
Styled HTML report with summary cards and detailed table (generated when `--format html` or `--format all` is used).

## Status Codes

- **OK**: Entry verified successfully with matching metadata
- **WARN**: Entry found but metadata inconsistencies detected
- **FAIL**: Entry could not be verified or strict mode violations

## Exit Codes

- `0`: Completed with no FAIL results
- `1`: Errors or one or more FAIL results

## Requirements

- Python 3.9+
- Internet connection (for API calls to Crossref and OpenAlex)

## License

MIT. See `LICENSE`.
