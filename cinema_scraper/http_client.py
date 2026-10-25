import logging
import threading
import time

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from . import config

logger = logging.getLogger(__name__)


class PoliteSession:
    """A requests session with retries and a per-thread delay between calls,
    so a multi-worker crawl doesn't hammer comingsoon.it faster than a single
    polite crawler would."""

    def __init__(self, delay: float = config.DEFAULT_DELAY):
        self.delay = delay
        self._local = threading.local()

    def _session(self) -> requests.Session:
        session = getattr(self._local, "session", None)
        if session is None:
            session = requests.Session()
            session.headers.update({"User-Agent": config.USER_AGENT})
            retry = Retry(
                total=config.MAX_RETRIES,
                backoff_factor=config.RETRY_BACKOFF,
                status_forcelist=[429, 500, 502, 503, 504],
                allowed_methods=["GET"],
            )
            adapter = HTTPAdapter(max_retries=retry)
            session.mount("https://", adapter)
            session.mount("http://", adapter)
            self._local.session = session
        return session

    def get(self, url: str, **kwargs) -> requests.Response:
        last_call = getattr(self._local, "last_call", 0.0)
        wait = self.delay - (time.monotonic() - last_call)
        if wait > 0:
            time.sleep(wait)
        try:
            response = self._session().get(url, timeout=config.REQUEST_TIMEOUT, **kwargs)
            response.raise_for_status()
            return response
        finally:
            self._local.last_call = time.monotonic()
