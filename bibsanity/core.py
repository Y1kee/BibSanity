"""Core verification logic."""

import asyncio
from typing import Dict, Any, List, Optional
from .providers import CrossrefProvider, OpenAlexProvider
from .utils import extract_doi, extract_title, extract_authors, extract_year
from .cache import Cache


class VerificationResult:
    """Result of verifying a BibTeX entry."""

    def __init__(
        self,
        entry_id: str,
        status: str,  # "OK", "WARN", "FAIL", "SKIP"
        reason: str,
        details: Optional[Dict[str, Any]] = None,
        confidence: float = 0.0,
    ):
        """Initialize verification result.

        Args:
            entry_id: BibTeX entry ID
            status: Verification status (OK, WARN, FAIL, SKIP)
            reason: Human-readable reason
            details: Additional details dictionary
            confidence: Confidence score (0.0-1.0, representing 0-100%)
        """
        self.entry_id = entry_id
        self.status = status
        self.reason = reason
        self.details = details or {}
        self.confidence = confidence


class Verifier:
    """Main verifier class implementing hybrid verification logic."""

    def __init__(
        self,
        cache: Cache,
        strict: bool = False,
        max_workers: int = 6,
    ):
        """Initialize verifier.

        Args:
            cache: Cache instance
            strict: Whether to use strict verification
            max_workers: Maximum concurrent workers
        """
        self.cache = cache
        self.strict = strict
        self.max_workers = max_workers
        self.crossref = CrossrefProvider(cache)
        self.openalex = OpenAlexProvider(cache)

    async def verify_entry(self, entry: Dict[str, Any]) -> VerificationResult:
        """Verify a single BibTeX entry.

        Args:
            entry: BibTeX entry dictionary

        Returns:
            VerificationResult
        """
        entry_id = entry.get("ID", "unknown")
        doi = extract_doi(entry)
        title = extract_title(entry)
        authors = extract_authors(entry)
        year = extract_year(entry)

        # Check if title is missing or empty - skip verification
        if not title or not title.strip():
            return VerificationResult(
                entry_id,
                "SKIP",
                "Missing title, cannot verify entry",
                {"doi": doi},
                confidence=0.0,
            )

        # Try DOI-based verification first
        if doi:
            result = await self._verify_via_doi(entry, doi, title, authors, year)
            if result is not None:
                # Return the result (OK or WARN)
                return result
            else:
                # DOI provided but lookup returned None - DOI doesn't exist
                return VerificationResult(
                    entry_id,
                    "FAIL",
                    "DOI not found in Crossref",
                    {"doi": doi, "title": title},
                    confidence=0.0,
                )

        # Fall back to title-based search
        if title:
            result = await self._verify_via_title(entry, title, authors, year)
            if result:
                return result

        # If we get here, verification failed (no DOI, no title match)
        return VerificationResult(
            entry_id,
            "WARN",
            "Could not verify entry: no DOI and title search found no matches",
            {"doi": doi, "title": title},
            confidence=0.0,
        )

    async def _verify_via_doi(
        self,
        entry: Dict[str, Any],
        doi: str,
        title: Optional[str],
        authors: List[str],
        year: Optional[int],
    ) -> Optional[VerificationResult]:
        """Verify entry using DOI lookup.

        Args:
            entry: BibTeX entry
            doi: DOI string
            title: Entry title
            authors: Entry authors
            year: Entry year

        Returns:
            VerificationResult or None if verification failed
        """
        work = await self.crossref.lookup_by_doi(doi)
        if not work:
            return None

        entry_id = entry.get("ID", "unknown")
        issues = []
        confidence = 1.0  # Start with 100% for DOI match

        # Check title match
        title_ratio = 1.0
        if title:
            api_title = work.get("title", [""])[0] if work.get("title") else None
            if api_title:
                from .utils import normalize_title
                from rapidfuzz import fuzz

                # Calculate title similarity ratio (case-insensitive)
                entry_title_norm = normalize_title(title).lower()
                api_title_norm = normalize_title(api_title).lower()
                title_ratio = (
                    fuzz.token_sort_ratio(entry_title_norm, api_title_norm)
                    / 100.0
                )
                if title_ratio < 0.85:
                    issues.append(f"Title mismatch (similarity: {title_ratio:.2f})")
                    confidence *= title_ratio  # Reduce confidence based on title similarity

        # Check year match (allow ±1 year difference for minor discrepancies)
        year_match = True
        if year:
            api_year = work.get("published-print", {}).get("date-parts", [[None]])[0][0]
            if not api_year:
                api_year = work.get("published-online", {}).get("date-parts", [[None]])[0][0]

            if api_year:
                year_diff = abs(api_year - year)
                if year_diff > 1:
                    issues.append(f"Year mismatch: entry={year}, API={api_year}")
                    year_match = False
                    # Reduce confidence for year mismatch (less severe than title)
                    confidence *= 0.85 if year_diff <= 2 else 0.70
                elif year_diff == 1:
                    # Minor year difference, slight reduction
                    confidence *= 0.95

        # Check authors (if available)
        author_match = True
        if authors and work.get("author"):
            api_authors = [
                f"{a.get('given', '')} {a.get('family', '')}".strip()
                for a in work.get("author", [])
            ]
            from .utils import match_authors

            if not match_authors(authors, api_authors):
                issues.append("Author list mismatch")
                author_match = False
                confidence *= 0.80  # Reduce confidence for author mismatch

        if issues:
            if self.strict:
                status = "FAIL"
            else:
                status = "WARN"
            return VerificationResult(
                entry_id,
                status,
                f"DOI verified but metadata inconsistencies: {', '.join(issues)}",
                {
                    "doi": doi,
                    "issues": issues,
                    "api_title": work.get("title", [""])[0] if work.get("title") else None,
                    "title_similarity": title_ratio,
                },
                confidence=max(0.0, min(1.0, confidence)),  # Clamp between 0 and 1
            )
        else:
            return VerificationResult(
                entry_id,
                "OK",
                "DOI verified and metadata matches",
                {"doi": doi, "title_similarity": title_ratio},
                confidence=1.0,  # 100% confidence for perfect DOI match
            )

    async def _verify_via_title(
        self,
        entry: Dict[str, Any],
        title: str,
        authors: List[str],
        year: Optional[int],
    ) -> Optional[VerificationResult]:
        """Verify entry using title search.

        Args:
            entry: BibTeX entry
            title: Entry title
            authors: Entry authors
            year: Entry year

        Returns:
            VerificationResult or None if verification failed
        """
        # Search for more results to ensure we find the best match
        # Short titles may match many papers, so we need more candidates
        results = await self.openalex.search_by_title(title, max_results=25)
        if not results:
            return None

        entry_id = entry.get("ID", "unknown")

        # Find best match
        best_match = None
        best_score = 0.0
        best_title_ratio = 0.0

        from rapidfuzz import fuzz
        from .utils import normalize_title

        for result in results:
            api_title = result.get("title", "")
            if not api_title:
                continue

            # Calculate title similarity ratio (case-insensitive)
            entry_title_norm = normalize_title(title).lower()
            api_title_norm = normalize_title(api_title).lower()
            title_ratio = (
                fuzz.token_sort_ratio(entry_title_norm, api_title_norm)
                / 100.0
            )

            # Check title similarity threshold
            # For very short titles (2-3 words), be more lenient
            title_words = len(entry_title_norm.split())
            min_threshold = 0.70 if title_words <= 3 else 0.75
            if title_ratio < min_threshold:
                continue

            # Calculate overall match score
            # Use a weighted scoring system that prioritizes metadata matches
            # For short titles, metadata matching becomes more important
            score = title_ratio * 0.4  # Base score from title similarity (40% weight)

            # Check year (allow ±1 year difference)
            # Year match is very important - give significant boost for exact/close match
            year_match_score = 0.0
            if year:
                api_year = result.get("publication_year")
                if api_year:
                    year_diff = abs(api_year - year)
                    if year_diff == 0:
                        year_match_score = 1.0  # Exact year match
                    elif year_diff == 1:
                        year_match_score = 0.9  # Close year match (±1 year)
                    elif year_diff <= 2:
                        year_match_score = 0.6  # Small mismatch (2 years)
                    elif year_diff <= 5:
                        year_match_score = 0.3  # Moderate mismatch (3-5 years)
                    else:
                        year_match_score = 0.0  # Large mismatch (>5 years)
                else:
                    year_match_score = 0.3  # No year in API, penalty
            else:
                year_match_score = 0.5  # No year in entry, neutral
            
            score += year_match_score * 0.35  # Year contributes 35% to total score

            # Check authors
            # Author match is also very important
            author_match_score = 0.5  # Default: neutral if no authors to check
            if authors and result.get("authorships"):
                api_authors = [
                    f"{a.get('author', {}).get('display_name', '')}"
                    for a in result.get("authorships", [])
                ]
                from .utils import match_authors

                if match_authors(authors, api_authors):
                    author_match_score = 1.0  # Author match
                else:
                    author_match_score = 0.1  # Author mismatch: significant penalty
            elif not authors:
                author_match_score = 0.5  # No authors in entry, neutral
            
            score += author_match_score * 0.25  # Authors contribute 25% to total score

            # Normalize score to [0, 1] range (should already be in range, but ensure)
            score = max(0.0, min(1.0, score))

            if score > best_score:
                best_score = score
                best_match = result
                best_title_ratio = title_ratio

        # Lower threshold to 0.5 to allow matches with good metadata even if title similarity is lower
        if best_match and best_score >= 0.5:
            issues = []
            is_strong_match = best_title_ratio >= 0.90  # Strong title match threshold
            
            # Calculate confidence based on title similarity and metadata matches
            confidence = best_title_ratio  # Start with title similarity
            
            if best_score < 1.0:
                if year:
                    api_year = best_match.get("publication_year")
                    if api_year:
                        year_diff = abs(api_year - year)
                        if year_diff > 1:
                            issues.append(f"Year mismatch: entry={year}, API={api_year}")
                            confidence *= 0.85 if year_diff <= 2 else 0.70
                        elif year_diff == 1:
                            confidence *= 0.95  # Minor year difference

                if authors and best_match.get("authorships"):
                    api_authors = [
                        f"{a.get('author', {}).get('display_name', '')}"
                        for a in best_match.get("authorships", [])
                    ]
                    from .utils import match_authors

                    if not match_authors(authors, api_authors):
                        issues.append("Author list mismatch")
                        confidence *= 0.80  # Reduce for author mismatch

            # Clamp confidence between 0 and 1
            confidence = max(0.0, min(1.0, confidence))

            # For strong title matches with minor issues, use OK or WARN
            # For weak matches, always WARN
            if is_strong_match and not issues:
                return VerificationResult(
                    entry_id,
                    "OK",
                    "Title match found and metadata matches (suggest adding DOI)",
                    {
                        "title": title,
                        "api_title": best_match.get("title"),
                        "match_score": best_score,
                        "title_similarity": best_title_ratio,
                    },
                    confidence=confidence,
                )
            elif is_strong_match and issues:
                # Strong match but minor metadata issues - WARN
                return VerificationResult(
                    entry_id,
                    "WARN",
                    f"Title match found but metadata inconsistencies: {', '.join(issues)} (suggest adding DOI)",
                    {
                        "title": title,
                        "api_title": best_match.get("title"),
                        "issues": issues,
                        "match_score": best_score,
                        "title_similarity": best_title_ratio,
                    },
                    confidence=confidence,
                )
            elif issues:
                # Weak match with issues - WARN
                status = "WARN" if not self.strict else "FAIL"
                return VerificationResult(
                    entry_id,
                    status,
                    f"Title match found but metadata inconsistencies: {', '.join(issues)}",
                    {
                        "title": title,
                        "api_title": best_match.get("title"),
                        "issues": issues,
                        "match_score": best_score,
                        "title_similarity": best_title_ratio,
                    },
                    confidence=confidence,
                )
            else:
                # Weak match but no issues - still WARN
                return VerificationResult(
                    entry_id,
                    "WARN",
                    "Title match found but similarity is weak",
                    {
                        "title": title,
                        "api_title": best_match.get("title"),
                        "match_score": best_score,
                        "title_similarity": best_title_ratio,
                    },
                    confidence=confidence,
                )

        return None

    async def verify_entries(
        self, entries: List[Dict[str, Any]], progress_callback=None
    ) -> List[VerificationResult]:
        """Verify multiple entries concurrently.

        Args:
            entries: List of BibTeX entries
            progress_callback: Optional callback function(completed, total, entry_id) for progress updates

        Returns:
            List of VerificationResult objects
        """
        semaphore = asyncio.Semaphore(self.max_workers)
        total = len(entries)
        completed_lock = asyncio.Lock()
        completed_count = 0

        async def verify_with_semaphore(entry):
            nonlocal completed_count
            async with semaphore:
                result = await self.verify_entry(entry)
                async with completed_lock:
                    completed_count += 1
                    if progress_callback:
                        # Call callback in a way that's safe for Rich progress bar
                        progress_callback(completed_count, total, entry.get("ID", "unknown"))
                return result

        tasks = [verify_with_semaphore(entry) for entry in entries]
        results = await asyncio.gather(*tasks)
        return results
