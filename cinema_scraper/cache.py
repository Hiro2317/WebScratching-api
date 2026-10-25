import json
import logging
import threading
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class JSONCache:
    """Thread-safe, disk-persisted key/value cache.

    Flushes to disk periodically (every `flush_every` writes) rather than on
    every single write, so a nationwide run doesn't do thousands of tiny
    file rewrites — call flush() explicitly at the end of a run too.
    """

    def __init__(self, path: str, flush_every: int = 20):
        self.path = Path(path)
        self._lock = threading.Lock()
        self._flush_every = flush_every
        self._dirty_count = 0
        self._data: Dict[str, Any] = self._load()

    def _load(self) -> Dict[str, Any]:
        if self.path.exists():
            try:
                with self.path.open("r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Cache file %s unreadable (%s); starting fresh.", self.path, exc)
        return {}

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            return self._data.get(key)

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._data[key] = value
            self._dirty_count += 1
            if self._dirty_count >= self._flush_every:
                self._flush_locked()

    def flush(self) -> None:
        with self._lock:
            self._flush_locked()

    def _flush_locked(self) -> None:
        tmp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        with tmp_path.open("w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)
        tmp_path.replace(self.path)
        self._dirty_count = 0
