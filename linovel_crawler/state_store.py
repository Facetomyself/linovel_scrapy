import json
import os
import threading
from typing import Iterable, Set


class LocalStateStore:
    """
    Lightweight local persistence for crawl progress.

    Stores a set of completed identifiers per spider to enable
    resume/skip behavior without requiring Redis/MySQL.
    """

    def __init__(self, path: str) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._completed: Set[str] = set()

        # Ensure parent directory exists
        os.makedirs(os.path.dirname(self.path), exist_ok=True)

    def load(self) -> None:
        """Load previously persisted completed keys from disk."""
        with self._lock:
            if not os.path.exists(self.path):
                self._completed.clear()
                return
            try:
                with open(self.path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                items = data.get('completed', []) if isinstance(data, dict) else []
                if isinstance(items, list):
                    self._completed = set(str(x) for x in items)
                else:
                    self._completed = set()
            except Exception:
                # Corrupted or unreadable file; start fresh
                self._completed = set()

    def save(self) -> None:
        """Persist current completed set to disk atomically."""
        with self._lock:
            tmp_path = f"{self.path}.tmp"
            data = {
                'completed': sorted(self._completed),
            }
            with open(tmp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False)
            os.replace(tmp_path, self.path)

    def add_completed(self, key: str) -> None:
        """Mark a key as completed in memory."""
        with self._lock:
            self._completed.add(key)

    def extend_completed(self, keys: Iterable[str]) -> None:
        with self._lock:
            self._completed.update(keys)

    def is_completed(self, key: str) -> bool:
        with self._lock:
            return key in self._completed

    def snapshot(self) -> Set[str]:
        with self._lock:
            return set(self._completed)

