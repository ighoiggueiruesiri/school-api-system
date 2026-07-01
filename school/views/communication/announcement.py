from rest_framework import viewsets, filters
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter, OpenApiTypes

from ...models import Announcement
from ...serializers import AnnouncementSerializer
from ..base import DynamicPageSizePagination, VersionedCacheMixin, is_admin, is_parent, is_staff


@extend_schema(tags=["Announcements"])
@extend_schema_view(
    list=extend_schema(
        summary="List announcements",
        parameters=[OpenApiParameter(name="page_size", description="Results per page", required=False, type=OpenApiTypes.INT)]
    ),
    create=extend_schema(summary="Post an announcement (Staff only)"),
    update=extend_schema(summary="Update an announcement (Staff only)"),
    partial_update=extend_schema(summary="Partially update an announcement (Staff only)"),
    destroy=extend_schema(summary="Delete an announcement (Admin only)"),
)
class AnnouncementViewSet(VersionedCacheMixin, viewsets.ModelViewSet):
    cache_resource     = "announcements"
    queryset           = Announcement.objects.none()
    serializer_class   = AnnouncementSerializer
    permission_classes = [IsAuthenticated]
    pagination_class   = DynamicPageSizePagination
    filter_backends    = [filters.SearchFilter]
    search_fields      = ["title", "body"]

    def _cache_discriminator(self, request) -> str:
        return "parent" if is_parent(request.user) else "staff"

    def get_queryset(self):
        user = self.request.user
        qs   = Announcement.objects.select_related("author")
        if is_parent(user):
            qs = qs.filter(audience__in=["all", "parents"])
        return qs.order_by('-id')

    def perform_create(self, serializer):
        if not is_staff(self.request.user):
            # FIX: was `raise PermissionError(...)` (built-in), which DRF does
            # not catch and results in a 500. Use DRF's PermissionDenied instead
            # so the framework returns a proper 403 response.
            raise PermissionDenied("Staff access required.")
        serializer.save(author=self.request.user)

    def update(self, request, *args, **kwargs):
        if not is_staff(request.user):
            raise PermissionDenied("Staff access required.")
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        if not is_admin(request.user):
            return Response({"error": "Only admins can delete announcements."}, status=403)
        return super().destroy(request, *args, **kwargs)