from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from django.core.cache import cache
from ..cache_utils import bump_cache_version, make_cache_key, CACHE_TTL

# ── PAGINATION ────────────────────────────────────────────────────────────────

class DynamicPageSizePagination(PageNumberPagination):
    """
    Supports ?page=N&page_size=N from the frontend.
    Returns { count, pages, next, previous, results } so the React
    pagination bar can display "1–10 of 47" without a second request.
    """
    page_size             = 10
    page_size_query_param = "page_size"
    max_page_size         = 200

    def get_paginated_response(self, data):
        return Response({
            "count":    self.page.paginator.count,
            "pages":    self.page.paginator.num_pages,
            "next":     self.get_next_link(),
            "previous": self.get_previous_link(),
            "results":  data,
        })


# ── CACHE VERSIONING MIXIN ────────────────────────────────────────────────────

class VersionedCacheMixin:
    """Versioned read-cache + automatic invalidation on writes."""

    cache_resource: str = ""   # subclass must set this

    # ── Key helpers ───────────────────────────────────────────────────────────

    def _cache_discriminator(self, request) -> str:
        return f"role:{request.user.role}"

    def _list_cache_key(self, request) -> str:
        params = request.META.get("QUERY_STRING", "")
        suffix = f"{self._cache_discriminator(request)}:list:{params}"
        return make_cache_key(self.cache_resource, suffix)

    def _retrieve_cache_key(self, request, pk) -> str:
        suffix = f"{self._cache_discriminator(request)}:retrieve:{pk}"
        return make_cache_key(self.cache_resource, suffix)

    # ── Read side ─────────────────────────────────────────────────────────────

    def list(self, request, *args, **kwargs):
        key    = self._list_cache_key(request)
        cached = cache.get(key)
        if cached is not None:
            return Response(cached)
        response = super().list(request, *args, **kwargs)
        cache.set(key, response.data, timeout=CACHE_TTL)
        return response

    def retrieve(self, request, *args, **kwargs):
        key    = self._retrieve_cache_key(request, kwargs.get("pk"))
        cached = cache.get(key)
        if cached is not None:
            return Response(cached)
        response = super().retrieve(request, *args, **kwargs)
        cache.set(key, response.data, timeout=CACHE_TTL)
        return response

    # ── Write side — bump version so all old cache entries are orphaned ───────

    def _bump(self):
        bump_cache_version(self.cache_resource)

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        if response.status_code in (200, 201):
            self._bump()
        return response

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        if response.status_code == 200:
            self._bump()
        return response

    def partial_update(self, request, *args, **kwargs):
        response = super().partial_update(request, *args, **kwargs)
        if response.status_code == 200:
            self._bump()
        return response

    def destroy(self, request, *args, **kwargs):
        response = super().destroy(request, *args, **kwargs)
        if response.status_code == 204:
            self._bump()
        return response


# ── ROLE HELPERS ──────────────────────────────────────────────────────────────

def is_admin(user):           return user.role == "admin"
def is_editor(user):          return user.role == "editor"
def is_admin_or_editor(user): return user.role in ("admin", "editor")
def is_staff(user):           return user.role in ("admin", "editor", "teacher", "non_academic")
def is_teacher(user):         return is_staff(user)   # kept for backward compat
def is_parent(user):          return user.role == "parent"
def is_pure_teacher(user):    return user.role == "teacher"