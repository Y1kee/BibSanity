"""API providers for verification (Crossref, OpenAlex)."""

import httpx
from typing import Optional, Dict, Any, List
from rapidfuzz import fuzz


class CrossrefProvider:
    """Crossref API provider for DOI-based verification."""

    BASE_URL = "https://api.crossref.org/works"

    def __init__(self, cache, timeout: float = 10.0):
        """Initialize Crossref provider.

        Args:
            cache: Cache instance
            timeout: Request timeout in seconds
        """
        self.cache = cache
        self.timeout = timeout

    async def lookup_by_doi(self, doi: str) -> Optional[Dict[str, Any]]:
        """Look up work by DOI.

        Args:
            doi: DOI string (with or without https://doi.org/)

        Returns:
            Work metadata or None if not found
        """
        # Normalize DOI
        doi = doi.strip()
        if doi.startswith("https://doi.org/"):
            doi = doi.replace("https://doi.org/", "")
        elif doi.startswith("http://dx.doi.org/"):
            doi = doi.replace("http://dx.doi.org/", "")
        elif doi.startswith("doi:"):
            doi = doi.replace("doi:", "")

        url = f"{self.BASE_URL}/{doi}"
        params = {}

        # Check cache
        cached = self.cache.get(url, params)
        if cached is not None:
            return cached

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                data = response.json()

                if data.get("status") == "ok" and "message" in data:
                    work = data["message"]
                    self.cache.set(url, params, work)
                    return work
        except (httpx.HTTPError, httpx.TimeoutException, KeyError):
            pass

        return None


class OpenAlexProvider:
    """OpenAlex API provider for title-based search."""

    BASE_URL = "https://api.openalex.org/works"

    def __init__(self, cache, timeout: float = 10.0):
        """Initialize OpenAlex provider.

        Args:
            cache: Cache instance
            timeout: Request timeout in seconds
        """
        self.cache = cache
        self.timeout = timeout

    async def search_by_title(
        self, title: str, max_results: int = 5
    ) -> List[Dict[str, Any]]:
        """Search works by title.

        Args:
            title: Title to search for
            max_results: Maximum number of results to return

        Returns:
            List of matching works
        """
        if not title or not title.strip():
            return []

        url = self.BASE_URL
        # Increase per_page to get more results for better matching
        # This helps when there are multiple papers with similar titles
        params = {
            "search": title,
            "per_page": min(max(max_results, 10), 25),  # At least 10 results for better matching
        }

        # Check cache
        cached = self.cache.get(url, params)
        if cached is not None:
            return cached

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                data = response.json()

                results = data.get("results", [])
                self.cache.set(url, params, results)
                return results
        except (httpx.HTTPError, httpx.TimeoutException, KeyError):
            pass

        return []

    def match_title(
        self, entry_title: str, candidate_title: str, threshold: float = 0.75
    ) -> bool:
        """Check if titles match using fuzzy matching.

        Args:
            entry_title: Title from BibTeX entry
            candidate_title: Title from API result
            threshold: Similarity threshold (0-1), default 0.75 for more lenient matching

        Returns:
            True if titles match
        """
        if not entry_title or not candidate_title:
            return False

        # Normalize titles (case-insensitive)
        entry_title = entry_title.lower().strip()
        candidate_title = candidate_title.lower().strip()

        # Use token sort ratio for better matching
        ratio = fuzz.token_sort_ratio(entry_title, candidate_title) / 100.0
        return ratio >= threshold
