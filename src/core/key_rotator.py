import time
import threading
from typing import List, Optional, Dict

class KeyRotator:
    """
    Thread-safe API Key Manager with automatic rotation, failure tracking,
    and temporary cool-down management.
    """

    def __init__(self, api_keys: List[str], cooldown_seconds: int = 60):
        self._raw_keys = [k.strip() for k in api_keys if k and k.strip()]
        self.cooldown_seconds = cooldown_seconds
        self._lock = threading.Lock()
        self._current_index = 0
        # Map: key -> cooldown_expiry_timestamp
        self._cooldowns: Dict[str, float] = {}

    @property
    def total_keys(self) -> int:
        return len(self._raw_keys)

    def add_key(self, api_key: str) -> None:
        key = api_key.strip()
        with self._lock:
            if key and key not in self._raw_keys:
                self._raw_keys.append(key)

    def get_key(self) -> Optional[str]:
        """
        Retrieves the next available key that is not in cool-down.
        Cycles in round-robin fashion. Returns None if all keys are cooling down.
        """
        with self._lock:
            if not self._raw_keys:
                return None

            now = time.time()
            # Clean expired cooldowns
            expired = [k for k, exp in self._cooldowns.items() if now >= exp]
            for k in expired:
                del self._cooldowns[k]

            # Try finding an available key starting from current_index
            total = len(self._raw_keys)
            for _ in range(total):
                candidate = self._raw_keys[self._current_index]
                self._current_index = (self._current_index + 1) % total

                if candidate not in self._cooldowns:
                    return candidate

            return None

    def mark_rate_limited(self, api_key: str, custom_cooldown: Optional[int] = None) -> None:
        """Puts a key into cool-down due to rate limits or quota constraints."""
        duration = custom_cooldown if custom_cooldown is not None else self.cooldown_seconds
        with self._lock:
            if api_key in self._raw_keys:
                self._cooldowns[api_key] = time.time() + duration

    def get_status(self) -> Dict[str, int]:
        """Returns statistics on active and cool-down keys."""
        with self._lock:
            now = time.time()
            cooling = sum(1 for exp in self._cooldowns.values() if exp > now)
            active = len(self._raw_keys) - cooling
            return {
                "total": len(self._raw_keys),
                "active": active,
                "in_cooldown": cooling
            }

