"""Utility functions for BibTeX parsing and matching."""

import bibtexparser
from bibtexparser.bparser import BibTexParser
from bibtexparser.customization import convert_to_unicode
from typing import Dict, Any, Optional, List
import re


def parse_bibtex(file_path: str) -> List[Dict[str, Any]]:
    """Parse BibTeX file and return entries.

    Args:
        file_path: Path to .bib file

    Returns:
        List of BibTeX entries
    """
    # Read and preprocess file to handle undefined macros
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Remove BibTeX comments (lines starting with % or inline % comments)
    # But preserve % in strings/braces
    lines = content.split('\n')
    processed_lines = []
    for line in lines:
        # Remove inline comments (but not % inside strings)
        if '%' in line:
            # Find the first % that's not inside quotes or braces
            in_string = False
            in_braces = 0
            comment_pos = -1
            for i, char in enumerate(line):
                if char == '"' and (i == 0 or line[i-1] != '\\'):
                    in_string = not in_string
                elif char == '{' and not in_string:
                    in_braces += 1
                elif char == '}' and not in_string:
                    in_braces -= 1
                elif char == '%' and not in_string and in_braces == 0:
                    comment_pos = i
                    break
            if comment_pos >= 0:
                line = line[:comment_pos].rstrip()
        processed_lines.append(line)
    content = '\n'.join(processed_lines)
    
    # Fix unquoted macro references: field = identifier, -> field = "identifier",
    # This handles cases like "booktitle = ecc," where ecc is an undefined macro
    # Simple regex: match = identifier, and quote it if not already quoted
    lines = content.split('\n')
    processed_lines = []
    for line in lines:
        # Match pattern: = identifier, where identifier is a simple word
        # Only replace if line doesn't already contain quotes or braces around the value
        if '=' in line:
            # Check if the value part (after =) is already quoted
            parts = line.split('=', 1)
            if len(parts) == 2:
                value_part = parts[1].strip()
                # If value is just an identifier followed by comma, quote it
                match = re.match(r'^([a-zA-Z][a-zA-Z0-9]*)\s*,?\s*$', value_part)
                if match and '"' not in value_part and '{' not in value_part:
                    line = parts[0] + '= "' + match.group(1) + '",'
        processed_lines.append(line)
    content = '\n'.join(processed_lines)
    
    from io import StringIO
    with StringIO(content) as f:
        parser = BibTexParser()
        parser.customization = convert_to_unicode
        parser.ignore_nonstandard_types = False
        parser.interpolate_strings = False  # Don't interpolate undefined strings
        try:
            bib_database = bibtexparser.load(f, parser=parser)
        except Exception:
            # If still fails, try with even more lenient settings
            f.seek(0)
            parser.ignore_nonstandard_types = True
            bib_database = bibtexparser.load(f, parser=parser)

    entries = []
    for entry in bib_database.entries:
        entries.append(entry)

    return entries


def normalize_title(title: str) -> str:
    """Normalize title for comparison.

    Args:
        title: Title string

    Returns:
        Normalized title
    """
    if not title:
        return ""

    # Remove extra whitespace
    title = " ".join(title.split())

    # Remove common LaTeX commands (basic)
    title = re.sub(r"\\[a-zA-Z]+\{([^}]+)\}", r"\1", title)
    title = re.sub(r"\{([^}]+)\}", r"\1", title)

    return title.strip()


def extract_doi(entry: Dict[str, Any]) -> Optional[str]:
    """Extract DOI from BibTeX entry.

    Args:
        entry: BibTeX entry dictionary

    Returns:
        DOI string or None
    """
    # Check various DOI fields
    for field in ["doi", "DOI"]:
        if field in entry:
            doi = entry[field]
            if doi:
                return str(doi).strip()

    return None


def extract_title(entry: Dict[str, Any]) -> Optional[str]:
    """Extract title from BibTeX entry.

    Args:
        entry: BibTeX entry dictionary

    Returns:
        Title string or None
    """
    for field in ["title", "Title"]:
        if field in entry:
            title = entry[field]
            if title:
                return normalize_title(str(title))

    return None


def extract_authors(entry: Dict[str, Any]) -> List[str]:
    """Extract authors from BibTeX entry.

    Args:
        entry: BibTeX entry dictionary

    Returns:
        List of author names
    """
    authors = []
    for field in ["author", "Author", "authors", "Authors"]:
        if field in entry:
            author_str = entry[field]
            if author_str:
                # Split by "and" (BibTeX standard)
                author_list = re.split(r"\s+and\s+", str(author_str), flags=re.IGNORECASE)
                authors.extend([a.strip() for a in author_list if a.strip()])

    return authors


def extract_year(entry: Dict[str, Any]) -> Optional[int]:
    """Extract year from BibTeX entry.

    Args:
        entry: BibTeX entry dictionary

    Returns:
        Year as integer or None
    """
    for field in ["year", "Year"]:
        if field in entry:
            try:
                year = int(entry[field])
                if 1000 <= year <= 2100:  # Reasonable range
                    return year
            except (ValueError, TypeError):
                pass

    return None


def match_authors(entry_authors: List[str], api_authors: List[str], threshold: float = 0.7) -> bool:
    """Check if author lists match.

    Args:
        entry_authors: Authors from BibTeX entry
        api_authors: Authors from API response
        threshold: Minimum match ratio

    Returns:
        True if authors match reasonably well
    """
    if not entry_authors or not api_authors:
        return True  # Can't verify if missing

    from rapidfuzz import fuzz

    # Normalize author names
    def normalize_author(name: str) -> str:
        return " ".join(name.lower().split())

    entry_normalized = [normalize_author(a) for a in entry_authors]
    api_normalized = [normalize_author(a) for a in api_authors]

    # Check if significant overlap exists
    matches = 0
    for entry_author in entry_normalized:
        for api_author in api_normalized:
            ratio = fuzz.token_sort_ratio(entry_author, api_author) / 100.0
            if ratio >= threshold:
                matches += 1
                break

    if not entry_normalized:
        return True

    match_ratio = matches / len(entry_normalized)
    return match_ratio >= 0.5  # At least half should match
