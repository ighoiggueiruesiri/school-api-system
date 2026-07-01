from rest_framework import viewsets, filters
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter, OpenApiTypes

from ...models import Assignment, Student
from ...serializers import AssignmentSerializer
from ..base import (
    DynamicPageSizePagination, VersionedCacheMixin,
    is_admin, is_parent, is_pure_teacher, is_staff,
)


@extend_schema(tags=["Assignments"])
@extend_schema_view(
    list=extend_schema(
        summary="List assignments",
        parameters=[
            OpenApiParameter(name="term",      description="Filter by term ID",          required=False, type=OpenApiTypes.INT),
            OpenApiParameter(name="type",      description="homework|classwork|project",  required=False, type=OpenApiTypes.STR),
            OpenApiParameter(name="page_size", description="Results per page",            required=False, type=OpenApiTypes.INT),
        ]
    ),
    create=extend_schema(summary="Create an assignment (Staff only)"),
    destroy=extend_schema(summary="Delete an assignment (Admin only)"),
)
class AssignmentViewSet(VersionedCacheMixin, viewsets.ModelViewSet):
    cache_resource     = "assignments"
    queryset           = Assignment.objects.none()
    serializer_class   = AssignmentSerializer
    permission_classes = [IsAuthenticated]
    pagination_class   = DynamicPageSizePagination
    filter_backends    = [filters.SearchFilter]
    search_fields      = ["title", "description"]

    def _cache_discriminator(self, request) -> str:
        if is_parent(request.user):
            return f"parent:{request.user.id}"
        if is_pure_teacher(request.user):
            return f"teacher:{request.user.id}"
        return "admin_editor"

    def get_queryset(self):
        user = self.request.user
        qs   = Assignment.objects.select_related("classroom", "teacher")

        if is_parent(user):
            classes = Student.objects.filter(
                parents=user, is_active=True
            ).values_list("current_class_id", flat=True)
            return qs.filter(classroom_id__in=classes).order_by('-id')

        if is_pure_teacher(user):
            return qs.filter(teacher=user).order_by('-id')

        term  = self.request.query_params.get("term")
        type_ = self.request.query_params.get("type")
        if term:  qs = qs.filter(term_id=term)
        if type_: qs = qs.filter(type=type_)
        return qs.order_by('-id')

    def perform_create(self, serializer):
        if not is_staff(self.request.user):
            raise PermissionError("Staff access required.")
        serializer.save(teacher=self.request.user)

    def destroy(self, request, *args, **kwargs):
        if not is_admin(request.user):
            return Response({"error": "Only admins can delete assignments."}, status=403)
        return super().destroy(request, *args, **kwargs)
