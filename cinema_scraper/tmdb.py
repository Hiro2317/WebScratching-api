import logging
import re
from dataclasses import dataclass
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from . import config
from .cache import JSONCache

logger = logging.getLogger(__name__)

_FORMAT_TAG_RE = re.compile(
    r"\b(3D|2D|4DX|IMAX|ISENSE|ATMOS|V\.O\.S?\.?|VO|VERSIONE ORIGINALE)\b",
    re.IGNORECASE,
)
_PARENS_RE = re.compile(r"[\(\[\{].*?[\)\]\}]")
_WHITESPACE_RE = re.compile(r"\s+")
_DATE_RE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")


def clean_title(raw_title: str) -> str:
    title = _FORMAT_TAG_RE.sub("", raw_title)
    title = _PARENS_RE.sub("", title)
    title = _WHITESPACE_RE.sub(" ", title)
    return title.strip()


def extract_year(uscita: Optional[str]) -> Optional[str]:
    if not uscita:
        return None
    match = _DATE_RE.search(uscita)
    return match.group(3) if match else None


@dataclass
class TmdbMatch:
    tmdb_id: Optional[int] = None
    imdb_id: Optional[str] = None
    canonical_title: Optional[str] = None
    original_title: Optional[str] = None
    poster: Optional[str] = None


class TmdbClient:
    def __init__(self, api_key: str = config.TMDB_API_KEY, cache: Optional[JSONCache] = None):
        self.api_key = api_key
        self.cache = cache
        self._warned_no_key = False
        self.session = requests.Session()
        retry = Retry(
            total=config.MAX_RETRIES,
            backoff_factor=config.RETRY_BACKOFF,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retry))

    def resolve(
        self,
        title: str,
        year: Optional[str] = None,
        cache_key: Optional[str] = None,
    ) -> TmdbMatch:
        """Resolve a film title (and optional release year) to TMDb + IMDb
        ids. `cache_key` should be the stable comingsoon.it film id when
        available — it's far more reliable than a title string for caching
        the same film across hundreds of cinemas."""
        if not self.api_key:
            # Don't cache a "no API key" placeholder: if the user sets
            # TMDB_API_KEY later and reruns, they should get real matches
            # instead of a permanently-cached null.
            return self._search(title, year)

        key = cache_key or f"title:{title.lower()}:{year or ''}"

        if self.cache is not None:
            cached = self.cache.get(key)
            if cached is not None:
                return TmdbMatch(**cached)

        result = self._search(title, year)
        if self.cache is not None:
            self.cache.set(key, result.__dict__)
        return result

    def _search(self, title: str, year: Optional[str]) -> TmdbMatch:
        if not self.api_key:
            if not self._warned_no_key:
                logger.warning("TMDB_API_KEY not set — skipping TMDb/IMDb matching.")
                self._warned_no_key = True
            return TmdbMatch(canonical_title=clean_title(title))

        cleaned = clean_title(title)
        if not cleaned:
            return TmdbMatch(canonical_title=title)

        params = {
            "api_key": self.api_key,
            "query": cleaned,
            "language": config.TMDB_LANGUAGE,
        }
        if year:
            params["primary_release_year"] = year

        try:
            resp = self.session.get(
                f"{config.TMDB_BASE_URL}/search/movie",
                params=params,
                timeout=config.REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            results = resp.json().get("results") or []
        except requests.RequestException as exc:
            logger.warning("TMDb search failed for %r: %s", cleaned, exc)
            return TmdbMatch(canonical_title=cleaned)

        if not results:
            return TmdbMatch(canonical_title=cleaned)

        best = results[0]
        tmdb_id = best.get("id")
        poster_path = best.get("poster_path")

        imdb_id = None
        if tmdb_id:
            imdb_id = self._external_ids(tmdb_id)

        return TmdbMatch(
            tmdb_id=tmdb_id,
            imdb_id=imdb_id,
            canonical_title=best.get("title"),
            original_title=best.get("original_title"),
            poster=f"{config.TMDB_IMAGE_BASE}{poster_path}" if poster_path else None,
        )

    def _external_ids(self, tmdb_id: int) -> Optional[str]:
        try:
            resp = self.session.get(
                f"{config.TMDB_BASE_URL}/movie/{tmdb_id}/external_ids",
                params={"api_key": self.api_key},
                timeout=config.REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            return resp.json().get("imdb_id")
        except requests.RequestException as exc:
            logger.warning("TMDb external_ids failed for id=%s: %s", tmdb_id, exc)
            return None
