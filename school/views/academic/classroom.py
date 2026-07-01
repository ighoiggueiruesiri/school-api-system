from django.db.models import Count, Q
from rest_framework import viewsets, filters
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter, OpenApiTypes

from ...models import ClassRoom
from ...serializers import ClassRoomSerializer
from ..base import DynamicPageSizePagination, VersionedCacheMixin, is_admin, is_admin_or_editor, is_pure_teacher


@extend_schema(tags=["Classrooms Management"])
@extend_schema_view(
    list=extend_schema(
        summary="List all classrooms",
        parameters=[OpenApiParameter(name="page_size", description="Results per page", required=False, type=OpenApiTypes.INT)]
    ),
    create=extend_schema(summary="Create a new classroom (Admin or Editor)"),
    retrieve=extend_schema(summary="Retrieve a specific classroom"),
    update=extend_schema(summary="Update a classroom (Admin or Editor)"),
    partial_update=extend_schema(summary="Partially update a classroom (Admin or Editor)"),
    destroy=extend_schema(summary="Delete a classroom (Admin only)"),
)
class ClassRoomViewSet(VersionedCacheMixin, viewsets.ModelViewSet):
    cache_resource     = "classrooms"
    queryset           = ClassRoom.objects.none()
    serializer_class   = ClassRoomSerializer
    permission_classes = [IsAuthenticated]
    pagination_class   = DynamicPageSizePagination
    filter_backends    = [filters.SearchFilter]
    search_fields      = ["name", "teacher__first_name", "teacher__last_name"]

    def _cache_discriminator(self, request) -> str:
        if is_pure_teacher(request.user):
            return f"teacher:{request.user.id}"
        return "all"

    def get_queryset(self):
        user    = self.request.user
        base_qs = ClassRoom.objects.annotate(
            student_count_annotated=Count("students", filter=Q(students__is_active=True))
        )
        if is_pure_teacher(user):
            return base_qs.filter(teacher=user).order_by('-id')
        return base_qs.order_by('-id')

    def create(self, request, *args, **kwargs):
        if not is_admin_or_editor(request.user):
            return Response({"error": "Admin or Editor access required."}, status=403)
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        if not is_admin_or_editor(request.user):
            return Response({"error": "Admin or Editor access required."}, status=403)
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        if not is_admin(request.user):
            return Response({"error": "Only admins can delete classrooms."}, status=403)
        return super().destroy(request, *args, **kwargs)
