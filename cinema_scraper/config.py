import os

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

try:
    # On some Windows setups (corporate AV/proxy TLS inspection), certifi's
    # bundled CA list doesn't include the locally-trusted root, even though
    # the OS trust store does. truststore makes the stdlib ssl module (and
    # therefore requests/urllib3) use the OS trust store instead.
    import truststore

    truststore.inject_into_ssl()
except ImportError:
    pass

BASE_URL = "https://www.comingsoon.it"
TROVACINEMA_URL = f"{BASE_URL}/cinema/trovacinema/"

# Honest, non-impersonating User-Agent. comingsoon.it's robots.txt disallows
# Claude/AnthropicBot only under /tag/, so /cinema/ is fair game; we still
# identify ourselves rather than spoofing a browser UA.
USER_AGENT = "ItalyCinemaScraperBot/1.0 (+personal, non-commercial data collection)"

REQUEST_TIMEOUT = 15  # seconds
DEFAULT_DELAY = 1.5  # polite delay between requests to comingsoon.it, per worker
DEFAULT_WORKERS = 4
MAX_RETRIES = 3
RETRY_BACKOFF = 1.5

TMDB_API_KEY = os.environ.get("TMDB_API_KEY", "")
TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w500"
TMDB_LANGUAGE = "it-IT"

# Links on /cinema/trovacinema/ that are navigation, not provinces.
NON_PROVINCE_SLUGS = {
    "news",
    "filmalcinema",
    "calendariouscite",
    "boxoffice",
    "video",
    "recensioni",
    "film-da-vedere",
    "trovacinema",
}

# Per ogni film scarica anche la pagina biglietti, che ha gli orari di tutti i giorni in
# programmazione (la scheda del cinema ha solo quelli di oggi). Una richiesta in più per film:
# lo scraping completo dura di più. FETCH_ALL_DAYS=0 per tornare ai soli orari di oggi.
FETCH_ALL_DAYS = os.environ.get("FETCH_ALL_DAYS", "1").strip().lower() not in ("0", "false", "no")

DEFAULT_OUTPUT_DIR = "output"
DEFAULT_CACHE_PATH = "tmdb_cache.json"
