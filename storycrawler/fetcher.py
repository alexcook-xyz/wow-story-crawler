# fetcher.py - polite, cached, resumable HTTP. Stdlib only.
#
# Rules (same spirit as tools/extract_prereqs.py): serial requests, a
# configurable delay between them, every body cached on disk so a crawl
# can be re-run offline, and 403/429 means that source stops for the
# rest of the run instead of retrying into a wall.
from __future__ import annotations

import hashlib
import time
import urllib.error
import urllib.request
from pathlib import Path

UA = {"User-Agent": "MainStoryGuide-storycrawler/0.1 "
                    "(offline research; single-threaded; cached)"}


class SourceBlocked(Exception):
    """Host answered 403/429: stop this source, keep the others."""


class FetchError(Exception):
    pass


class Fetcher:
    def __init__(self, cache_dir: Path, delay: float = 2.0,
                 offline: bool = False, dry_run: bool = False,
                 timeout: int = 30, max_retries: int = 2,
                 sleep=time.sleep, now=time.monotonic):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.delay = delay
        self.offline = offline
        self.dry_run = dry_run
        self.timeout = timeout
        self.max_retries = max_retries
        self._sleep = sleep
        self._now = now
        self._last_at: dict[str, float] = {}
        self.blocked: set[str] = set()
        self.planned: list[str] = []      # dry-run: URLs we WOULD fetch
        self.stats = {"fetched": 0, "cached": 0, "failed": 0}

    def _cache_file(self, source: str, url: str) -> Path:
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
        safe = url.rstrip("/").rsplit("/", 1)[-1].replace("=", "_")
        return self.cache_dir / f"{source}_{safe}_{digest}.html"

    def fetch(self, source: str, url: str) -> str | None:
        """Return page HTML, or None when unavailable (offline miss,
        dry-run, blocked source, or exhausted retries)."""
        cached = self._cache_file(source, url)
        if cached.exists():
            self.stats["cached"] += 1
            return cached.read_text(encoding="utf-8", errors="replace")
        if self.offline:
            return None
        if source in self.blocked:
            return None
        if self.dry_run:
            self.planned.append(url)
            return None
        self._pace(source)
        last_err: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                req = urllib.request.Request(url, headers=UA)
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    body = r.read().decode("utf-8", "replace")
                cached.write_text(body, encoding="utf-8")
                self.stats["fetched"] += 1
                return body
            except urllib.error.HTTPError as e:
                if e.code in (403, 429):
                    self.blocked.add(source)
                    raise SourceBlocked(f"{source}: HTTP {e.code} at {url}")
                if e.code == 404:
                    self.stats["failed"] += 1
                    return None
                last_err = e
            except urllib.error.URLError as e:
                last_err = e
            if attempt < self.max_retries:
                self._sleep(self.delay * (attempt + 1))
        self.stats["failed"] += 1
        raise FetchError(f"{source}: {url}: {last_err}")

    def _pace(self, source: str) -> None:
        last = self._last_at.get(source)
        if last is not None:
            wait = self.delay - (self._now() - last)
            if wait > 0:
                self._sleep(wait)
        self._last_at[source] = self._now()
