import argparse
import logging
import sys

from . import config
from .pipeline import run_pipeline


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Scrape film programming from comingsoon.it and match each "
        "title to its TMDb/IMDb id."
    )
    parser.add_argument(
        "--province",
        action="append",
        dest="provinces",
        metavar="SLUG",
        help="Province slug to scrape (e.g. 'forli', 'roma'). Repeatable. "
        "Omit to scrape every province in Italy.",
    )
    parser.add_argument(
        "--output-dir",
        default=config.DEFAULT_OUTPUT_DIR,
        help=f"Directory for per-province JSON output (default: {config.DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--cache-path",
        default=config.DEFAULT_CACHE_PATH,
        help=f"Path to the persistent TMDb match cache (default: {config.DEFAULT_CACHE_PATH})",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=config.DEFAULT_WORKERS,
        help=f"Concurrent worker threads per province (default: {config.DEFAULT_WORKERS})",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=config.DEFAULT_DELAY,
        help=f"Minimum delay in seconds between requests, per worker (default: {config.DEFAULT_DELAY})",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only scrape the first N provinces (useful for testing).",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Re-scrape provinces even if an output file already exists for them.",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable debug logging."
    )
    return parser


def main(argv=None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if not config.TMDB_API_KEY:
        logging.getLogger(__name__).warning(
            "TMDB_API_KEY is not set — output will have tmdb_id/imdb_id as null. "
            "Set it in the environment or in a .env file (see .env.example)."
        )

    written = run_pipeline(
        province_slugs=args.provinces,
        output_dir=args.output_dir,
        cache_path=args.cache_path,
        workers=args.workers,
        delay=args.delay,
        resume=not args.no_resume,
        limit=args.limit,
    )

    print(f"Done. {len(written)} province file(s) in {args.output_dir}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
