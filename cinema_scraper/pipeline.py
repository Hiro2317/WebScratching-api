import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from pathlib import Path
from typing import Iterable, List, Optional

from . import comingsoon, config
from .cache import JSONCache
from .http_client import PoliteSession
from .tmdb import TmdbClient, extract_year

logger = logging.getLogger(__name__)


def _enrich_screening(screening: comingsoon.Screening, tmdb_client: TmdbClient) -> dict:
    title = screening.original_title or screening.raw_title
    year = extract_year(screening.uscita)
    cache_key = (
        f"cs:{screening.comingsoon_film_id}" if screening.comingsoon_film_id else None
    )
    match = tmdb_client.resolve(title, year=year, cache_key=cache_key)

    data = asdict(screening)
    data["tmdb_id"] = match.tmdb_id
    data["imdb_id"] = match.imdb_id
    data["tmdb_canonical_title"] = match.canonical_title
    data["poster"] = match.poster
    return data


def scrape_cinema(
    session: PoliteSession,
    tmdb_client: TmdbClient,
    cinema: comingsoon.CinemaRef,
) -> dict:
    program = comingsoon.get_cinema_program(session, cinema)
    return {
        "name": program.name,
        "source_url": program.url,
        "address": program.address,
        "city": program.city,
        "province_code": program.province_code,
        "phone": program.phone,
        "movies": [_enrich_screening(s, tmdb_client) for s in program.screenings],
    }


def scrape_province(
    session: PoliteSession,
    tmdb_client: TmdbClient,
    province: comingsoon.Province,
    workers: int = config.DEFAULT_WORKERS,
) -> dict:
    cinemas = comingsoon.list_cinemas(session, province)
    logger.info("[%s] %d cinema(s) found", province.name, len(cinemas))

    results = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(scrape_cinema, session, tmdb_client, cinema): cinema
            for cinema in cinemas
        }
        for future in as_completed(futures):
            cinema = futures[future]
            try:
                results.append(future.result())
            except Exception as exc:  # noqa: BLE001 - keep crawling other cinemas
                logger.error("[%s] failed on %s: %s", province.name, cinema.url, exc)

    return {
        "timestamp": int(time.time()),
        "province": province.slug,
        "province_name": province.name,
        "total_cinemas": len(results),
        "cinemas": results,
    }


def run_pipeline(
    province_slugs: Optional[Iterable[str]] = None,
    output_dir: str = config.DEFAULT_OUTPUT_DIR,
    cache_path: str = config.DEFAULT_CACHE_PATH,
    workers: int = config.DEFAULT_WORKERS,
    delay: float = config.DEFAULT_DELAY,
    resume: bool = True,
    limit: Optional[int] = None,
) -> List[Path]:
    """Scrape all requested provinces (or every province in Italy if
    province_slugs is None) and write one JSON file per province to
    output_dir. Returns the list of files written or already present."""
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    session = PoliteSession(delay=delay)
    tmdb_cache = JSONCache(cache_path)
    tmdb_client = TmdbClient(cache=tmdb_cache)

    all_provinces = comingsoon.list_provinces(session)
    logger.info("Found %d provinces on comingsoon.it", len(all_provinces))

    if province_slugs:
        wanted = {s.lower() for s in province_slugs}
        provinces = [p for p in all_provinces if p.slug in wanted]
        missing = wanted - {p.slug for p in provinces}
        if missing:
            logger.warning("Unknown province slug(s) ignored: %s", ", ".join(sorted(missing)))
    else:
        provinces = all_provinces

    if limit:
        provinces = provinces[:limit]

    written: List[Path] = []
    try:
        for province in provinces:
            out_file = out_dir / f"{province.slug}.json"
            if resume and out_file.exists():
                logger.info("[%s] already scraped, skipping (resume=True)", province.name)
                written.append(out_file)
                continue

            data = scrape_province(session, tmdb_client, province, workers=workers)
            with out_file.open("w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            written.append(out_file)
            logger.info("[%s] saved -> %s", province.name, out_file)
    finally:
        tmdb_cache.flush()

    return written
