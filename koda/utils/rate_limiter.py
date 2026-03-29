"""Token bucket rate limiter replacing the duplicated sliding window.

Uses aiolimiter for proper async rate limiting.
"""

from collections import OrderedDict

from aiolimiter import AsyncLimiter

from koda.config import RATE_LIMIT_PER_MINUTE

_MAX_CACHED_LIMITERS = 100

# Per-user rate limiters with LRU eviction to prevent unbounded growth.
_user_limiters: OrderedDict[int, AsyncLimiter] = OrderedDict()


def get_limiter(user_id: int) -> AsyncLimiter:
    """Get or create a rate limiter for a user."""
    if user_id in _user_limiters:
        _user_limiters.move_to_end(user_id)
        return _user_limiters[user_id]
    if len(_user_limiters) >= _MAX_CACHED_LIMITERS:
        _user_limiters.popitem(last=False)
    _user_limiters[user_id] = AsyncLimiter(RATE_LIMIT_PER_MINUTE, 60)
    return _user_limiters[user_id]


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
