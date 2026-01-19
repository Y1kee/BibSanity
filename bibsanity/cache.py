"""Caching utilities for API responses."""

import json
import hashlib
from pathlib import Path
from typing import Optional, Any
from platformdirs import user_cache_dir


class Cache:
    """Simple file-based cache for API responses."""

    def __init__(self, enabled: bool = True):
        """Initialize cache.

        Args:
            enabled: Whether caching is enabled
        """
        self.enabled = enabled
        if enabled:
            cache_dir = Path(user_cache_dir("bibsanity", "bibsanity"))
            cache_dir.mkdir(parents=True, exist_ok=True)
            self.cache_dir = cache_dir
        else:
            self.cache_dir = None

    def _get_key(self, url: str, params: dict) -> str:
        """Generate cache key from URL and parameters."""
        key_data = f"{url}:{json.dumps(params, sort_keys=True)}"
        return hashlib.sha256(key_data.encode()).hexdigest()

    def get(self, url: str, params: dict) -> Optional[Any]:
        """Get cached response if available.

        Args:
            url: API URL
            params: Request parameters

        Returns:
            Cached response data or None
        """
        if not self.enabled or self.cache_dir is None:
            return None

        cache_key = self._get_key(url, params)
        cache_file = self.cache_dir / f"{cache_key}.json"

        if cache_file.exists():
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                return None

        return None

    def set(self, url: str, params: dict, data: Any) -> None:
        """Cache response data.

        Args:
            url: API URL
            params: Request parameters
            data: Response data to cache
        """
        if not self.enabled or self.cache_dir is None:
            return

        cache_key = self._get_key(url, params)
        cache_file = self.cache_dir / f"{cache_key}.json"

        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except IOError:
            pass  # Silently fail if cache write fails
