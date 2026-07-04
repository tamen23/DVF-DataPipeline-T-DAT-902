from __future__ import annotations

import random
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Iterator

import requests

# Rotate user agents to reduce detection risk
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
]


class BaseScraper(ABC):
    """
    Base class for all listing scrapers.
    Handles rate limiting, retries, and produces standardized listing dicts.
    """

    source: str  # must be set by subclasses
    base_delay: float = 2.0   # seconds between requests
    jitter: float = 1.5       # random extra delay range

    def __init__(self) -> None:
        self.session = requests.Session()
        self._set_headers()

    def _set_headers(self) -> None:
        self.session.headers.update({
            "User-Agent": random.choice(USER_AGENTS),
            "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })

    def _get(self, url: str, **kwargs) -> requests.Response:
        """GET with rate limiting and retry."""
        time.sleep(self.base_delay + random.uniform(0, self.jitter))
        self._set_headers()  # rotate user agent on each request

        for attempt in range(3):
            try:
                response = self.session.get(url, timeout=30, **kwargs)
                if response.status_code == 429:
                    wait = 60 * (attempt + 1)
                    print(f"  [rate limit] waiting {wait}s before retry...")
                    time.sleep(wait)
                    continue
                response.raise_for_status()
                return response
            except requests.RequestException as e:
                if attempt == 2:
                    raise
                time.sleep(10 * (attempt + 1))
        raise RuntimeError("Max retries exceeded")

    def _normalize(self, raw: dict) -> dict:
        """Attach metadata common to all sources."""
        return {
            **raw,
            "source": self.source,
            "scraped_at": datetime.now(timezone.utc).isoformat(),
        }

    @abstractmethod
    def scrape(self, location: str, pages: int = 5) -> Iterator[dict]:
        """Yield one normalized listing dict per result."""
        ...
