"""Token bucket rate limiter replacing the duplicated sliding window.

Uses aiolimiter for proper async rate limiting.
TTL-based eviction ensures active users keep their token buckets while
stale entries are cleaned up, preventing rate-limit bypass via LRU churn.
"""

import time

from aiolimiter import AsyncLimiter

from koda.config import RATE_LIMIT_PER_MINUTE

_MAX_CACHED_LIMITERS = 1000
_LIMITER_TTL_SECONDS = 300  # 5 minutes
_SWEEP_THRESHOLD = _MAX_CACHED_LIMITERS // 2

# Per-user rate limiters with TTL-based eviction.
# Values are (limiter, last_access_monotonic) tuples.
_user_limiters: dict[int, tuple[AsyncLimiter, float]] = {}
_call_count: int = 0


def _sweep_stale() -> None:
    """Remove entries older than the TTL."""
    cutoff = time.monotonic() - _LIMITER_TTL_SECONDS
    stale = [uid for uid, (_, ts) in _user_limiters.items() if ts < cutoff]
    for uid in stale:
        del _user_limiters[uid]


def get_limiter(user_id: int) -> AsyncLimiter:
    """Get or create a rate limiter for a user."""
    global _call_count
    _call_count += 1

    now = time.monotonic()

    # Periodic sweep: only when the cache is large enough to matter.
    if _call_count % 50 == 0 or len(_user_limiters) >= _SWEEP_THRESHOLD:
        _sweep_stale()

    entry = _user_limiters.get(user_id)
    if entry is not None:
        limiter, _ = entry
        _user_limiters[user_id] = (limiter, now)
        return limiter

    # Safety-net cap: if still over limit after sweep, drop oldest entries.
    if len(_user_limiters) >= _MAX_CACHED_LIMITERS:
        _sweep_stale()
        # If still over, evict oldest by timestamp.
        while len(_user_limiters) >= _MAX_CACHED_LIMITERS:
            oldest_uid = min(_user_limiters, key=lambda k: _user_limiters[k][1])
            del _user_limiters[oldest_uid]

    limiter = AsyncLimiter(RATE_LIMIT_PER_MINUTE, 60)
    _user_limiters[user_id] = (limiter, now)
    return limiter


async def check_rate_limit(user_id: int) -> bool:
    """Check if user is within rate limit. Returns True if allowed."""
    limiter = get_limiter(user_id)
    return bool(limiter.has_capacity())


async def acquire_rate_limit(user_id: int) -> bool:
    """Try to acquire a rate limit token. Returns True if acquired."""
    limiter = get_limiter(user_id)
    if not limiter.has_capacity():
        return False
    await limiter.acquire()
    return True
