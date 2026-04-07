"""Configuration for response cache and script library."""

from koda.config import _env

# --- Response Cache ---
CACHE_ENABLED: bool = _env("CACHE_ENABLED", "true").lower() == "true"
CACHE_TTL_DAYS: int = int(_env("CACHE_TTL_DAYS", "7"))
CACHE_MAX_ENTRIES_PER_USER: int = int(_env("CACHE_MAX_ENTRIES_PER_USER", "500"))
CACHE_FUZZY_THRESHOLD: float = float(_env("CACHE_FUZZY_THRESHOLD", "0.92"))
CACHE_FUZZY_SUGGEST_THRESHOLD: float = float(_env("CACHE_FUZZY_SUGGEST_THRESHOLD", "0.80"))
CACHE_LOOKUP_TIMEOUT: float = float(_env("CACHE_LOOKUP_TIMEOUT", "2.0"))
CACHE_CLEANUP_HOUR: int = int(_env("CACHE_CLEANUP_HOUR", "4"))
CACHE_SEMANTIC_LIMIT: int = int(_env("CACHE_SEMANTIC_LIMIT", "64"))
CACHE_SEMANTIC_CHUNK_SIZE: int = int(_env("CACHE_SEMANTIC_CHUNK_SIZE", "8"))

# --- Script Library ---
SCRIPT_LIBRARY_ENABLED: bool = _env("SCRIPT_LIBRARY_ENABLED", "true").lower() == "true"
SCRIPT_MAX_PER_USER: int = int(_env("SCRIPT_MAX_PER_USER", "200"))
SCRIPT_SEARCH_THRESHOLD: float = float(_env("SCRIPT_SEARCH_THRESHOLD", "0.70"))
SCRIPT_SEARCH_MAX_RESULTS: int = int(_env("SCRIPT_SEARCH_MAX_RESULTS", "5"))
SCRIPT_AUTO_EXTRACT: bool = _env("SCRIPT_AUTO_EXTRACT", "true").lower() == "true"
SCRIPT_LOOKUP_TIMEOUT: float = float(_env("SCRIPT_LOOKUP_TIMEOUT", "2.0"))
