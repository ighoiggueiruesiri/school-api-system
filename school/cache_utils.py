"""
school/cache_utils.py
─────────────────────────────────────────────────────────────────────────────
Cache Versioning — fast reads, instantly fresh writes.

HOW IT WORKS
────────────
Every resource (classrooms, terms, announcements…) has a version counter
stored in cache under the key  "cv:<resource>".

  • Reads  → include the current version in the cache key.
  • Writes → atomically increment the version counter.

After a write, every previously cached entry for that resource has a stale
version number baked into its key, so it is simply never looked up again.
The old entries expire quietly when their 15-minute TTL runs out — no
explicit deletion, no signal magic, no opaque URL-key hunting.

USAGE (in views.py via VersionedCacheMixin — you don't call these directly)
────────────
    from .cache_utils import bump_cache_version, make_cache_key, CACHE_TTL
    from django.core.cache import cache

    # Read path
    key    = make_cache_key("classrooms", discriminator_string)
    cached = cache.get(key)

    # Write path (after any create / update / destroy)
    bump_cache_version("classrooms")
"""

import hashlib
from django.core.cache import cache

# ── TTL ───────────────────────────────────────────────────────────────────────

CACHE_TTL: int = 60 * 15          # 15 minutes (matches original @cache_page TTL)
_VERSION_TTL: int = 60 * 60 * 24  # version counters live for 24 hours


# ── Version counter ───────────────────────────────────────────────────────────

def get_cache_version(resource: str) -> int:
    """
    Return the active version number for *resource*.
    Defaults to 1 if the counter has never been set (e.g. after a cold start
    or full cache flush) — guarantees a valid integer at all times.
    """
    return cache.get(f"cv:{resource}", 1)


def bump_cache_version(resource: str) -> int:
    """
    Atomically increment the version counter for *resource*.

    All cache entries previously built with the old version number are now
    unreachable — they will expire on their own TTL without ever being served.

    Returns the new version number.
    """
    version_key = f"cv:{resource}"
    try:
        # incr() is atomic on both Redis and Memcached.
        return cache.incr(version_key)
    except ValueError:
        # Key did not exist yet (e.g. first write after a cache flush).
        # Set to 2 so that the implicit default-1 entries used during the cold
        # start are orphaned immediately.
        new_version = 2
        cache.set(version_key, new_version, timeout=_VERSION_TTL)
        return new_version


# ── Key builder ───────────────────────────────────────────────────────────────

def make_cache_key(resource: str, suffix: str) -> str:
    """
    Build a versioned, length-safe cache key.

    Format:  v{version}:{resource}:{md5(suffix)[:16]}

    *suffix* is hashed so the key stays well within the 250-character limit
    of Memcached (and similarly short on Redis), even when query strings are
    long.  The hash is NOT used for security — hence usedforsecurity=False.
    """
    version     = get_cache_version(resource)
    suffix_hash = hashlib.md5(suffix.encode(), usedforsecurity=False).hexdigest()[:16]
    return f"v{version}:{resource}:{suffix_hash}"
