import functools
import hashlib
import json
import logging
from datetime import UTC, datetime, timedelta

log = logging.getLogger(__name__)


class CacheClient:
    def __init__(self, supabase):
        self._supabase = supabase

    def get_cache(self, table, key):
        cache = (
            self._supabase.table(table)
            .select('*')
            .eq("cache_key", key)
            .gt("expires_at", datetime.now(UTC).isoformat())
            .execute()
        )
        return cache.data[0]["data"] if cache.data else None

    def set_cache(self, table, key, value, ttl_seconds):
        expires_at = (datetime.now(UTC) + timedelta(seconds=ttl_seconds)).isoformat()
        self._supabase.table(table).upsert({
            "cache_key": key,
            "data": value,
            "expires_at": expires_at,
        }).execute()

    def to_hash(self, value: str | dict) -> str:
        if isinstance(value, dict):
            value = json.dumps(value, sort_keys=True).encode()
        else:
            value = value.encode()
        return hashlib.sha256(value).hexdigest()
    

def cached(table, key_fn, ttl_seconds):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            key_input = key_fn(*args, **kwargs)
            cache_key = self._cache.to_hash(key_input)

            cached_result = self._cache.get_cache(table, cache_key)
            if cached_result:
                log.info(f"cache hit for #{key_input}")
                return cached_result

            result = func(self, *args, **kwargs)

            self._cache.set_cache(table, cache_key, result, ttl_seconds)
            return result
        return wrapper
    return decorator