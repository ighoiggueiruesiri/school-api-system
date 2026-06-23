from rest_framework import viewsets, filters, status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter, OpenApiTypes

from ..models import Announcement, Inquiry
from ..serializers import AnnouncementSerializer, InquirySerializer
from .base import DynamicPageSizePagination, VersionedCacheMixin, is_admin, is_parent, is_staff

@extend_schema(tags=["Announcements"])
@extend_schema_view(
    list=extend_schema(
        summary="List announcements",
        parameters=[OpenApiParameter(name="page_size", description="Results per page", required=False, type=OpenApiTypes.INT)]
    ),
    create=extend_schema(summary="Post an announcement (Staff only)"),
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
        qs = Announcement.objects.select_related("author")
        if is_parent(user):
            qs = qs.filter(audience__in=["all", "parents"])
        return qs.order_by('-id')

    def perform_create(self, serializer):
        if not is_staff(self.request.user):
            raise PermissionError("Staff access required.")
        serializer.save(author=self.request.user)

    def destroy(self, request, *args, **kwargs):
        if not is_admin(request.user):
            return Response({"error": "Only admins can delete announcements."}, status=403)
        return super().destroy(request, *args, **kwargs)


@extend_schema(tags=["Lead Capture"])
@extend_schema_view(
    create=extend_schema(
        summary="Submit a public lead/inquiry",
        description="Public endpoint for the website popup. No authentication required.",
        auth=[],
    ),
    list=extend_schema(summary="List all inquiries (Staff only)"),
    retrieve=extend_schema(summary="Get specific inquiry details (Staff only)"),
    update=extend_schema(summary="Update an inquiry (Staff only)"),
    partial_update=extend_schema(summary="Partially update an inquiry (Staff only)"),
    destroy=extend_schema(summary="Delete an inquiry (Staff only)"),
)
class InquiryViewSet(viewsets.ModelViewSet):
    queryset         = Inquiry.objects.all().order_by('-created_at')
    serializer_class = InquirySerializer
    pagination_class = DynamicPageSizePagination
    filter_backends  = [filters.SearchFilter]
    search_fields    = ["parent_name", "email", "phone"]

    def get_permissions(self):
        if self.action == 'create':
            return [AllowAny()]
        return [IsAuthenticated()]