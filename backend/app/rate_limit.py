import os
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Callable

from fastapi import HTTPException


def _positive_int(name: str, default: int) -> int:
    raw_value = os.getenv(name, str(default))
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if value <= 0:
        raise RuntimeError(f"{name} must be greater than zero")
    return value


@dataclass(frozen=True)
class ApiRateLimitSettings:
    customer_join_limit: int
    customer_join_window_seconds: int
    customer_order_limit: int
    customer_order_window_seconds: int
    staff_order_limit: int
    staff_order_window_seconds: int
    customer_selection_limit: int
    customer_selection_window_seconds: int
    max_keys: int


def get_api_rate_limit_settings() -> ApiRateLimitSettings:
    return ApiRateLimitSettings(
        customer_join_limit=_positive_int("CUSTOMER_JOIN_RATE_LIMIT", 10),
        customer_join_window_seconds=_positive_int("CUSTOMER_JOIN_RATE_WINDOW_SECONDS", 60),
        customer_order_limit=_positive_int("CUSTOMER_ORDER_RATE_LIMIT", 5),
        customer_order_window_seconds=_positive_int("CUSTOMER_ORDER_RATE_WINDOW_SECONDS", 60),
        staff_order_limit=_positive_int("STAFF_ORDER_RATE_LIMIT", 10),
        staff_order_window_seconds=_positive_int("STAFF_ORDER_RATE_WINDOW_SECONDS", 60),
        customer_selection_limit=_positive_int("CUSTOMER_SELECTION_RATE_LIMIT", 60),
        customer_selection_window_seconds=_positive_int("CUSTOMER_SELECTION_RATE_WINDOW_SECONDS", 60),
        max_keys=_positive_int("API_RATE_LIMIT_MAX_KEYS", 10_000),
    )


class SlidingWindowRateLimiter:
    """Thread-safe, process-local sliding-window limiter with bounded key storage."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._attempts: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def reset(self) -> None:
        with self._lock:
            self._attempts.clear()

    def check_and_record(self, key: str, limit: int, window_seconds: int, max_keys: int) -> None:
        now = self._clock()
        cutoff = now - window_seconds
        with self._lock:
            attempts = self._attempts.get(key)
            if attempts is not None:
                while attempts and attempts[0] <= cutoff:
                    attempts.popleft()
                if not attempts:
                    del self._attempts[key]
                    attempts = None

            if attempts is None:
                if len(self._attempts) >= max_keys:
                    oldest_key = min(
                        self._attempts,
                        key=lambda current: self._attempts[current][-1],
                    )
                    del self._attempts[oldest_key]
                attempts = deque()
                self._attempts[key] = attempts

            if len(attempts) >= limit:
                retry_after = max(1, int(attempts[0] + window_seconds - now) + 1)
                raise HTTPException(
                    status_code=429,
                    detail="リクエスト回数が上限に達しました。しばらくしてから再試行してください",
                    headers={"Retry-After": str(retry_after)},
                )
            attempts.append(now)


api_rate_limiter = SlidingWindowRateLimiter()
