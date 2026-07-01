from rest_framework import viewsets, filters
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter, OpenApiTypes, inline_serializer
from rest_framework import serializers as drf_serializers

from ...models import AcademicReport
from ...serializers import AcademicReportSerializer, AcademicReportListSerializer
from ..base import (
    DynamicPageSizePagination, VersionedCacheMixin,
    is_admin, is_parent, is_pure_teacher, is_staff,
)


@extend_schema(tags=["Academic Reports"])
@extend_schema_view(
    list=extend_schema(
        summary="List academic reports",
        parameters=[
            OpenApiParameter(name="student",      description="Filter by student ID",    required=False, type=OpenApiTypes.STR),
            OpenApiParameter(name="term",         description="Filter by term ID",       required=False, type=OpenApiTypes.INT),
            OpenApiParameter(name="classroom",    description="Filter by classroom ID",  required=False, type=OpenApiTypes.INT),
            OpenApiParameter(name="is_published", description="true | false",            required=False, type=OpenApiTypes.BOOL),
            OpenApiParameter(name="report_type",  description="preschool | elementary",  required=False, type=OpenApiTypes.STR),
            OpenApiParameter(name="page_size",    description="Results per page",        required=False, type=OpenApiTypes.INT),
        ]
    ),
    create=extend_schema(summary="Create an academic report (Staff only)"),
    retrieve=extend_schema(summary="Retrieve full academic report (with subject scores)"),
    update=extend_schema(summary="Update an academic report (Staff only)"),
    partial_update=extend_schema(summary="Partially update an academic report"),
    destroy=extend_schema(summary="Delete a report (Admin only)"),
)
class AcademicReportViewSet(VersionedCacheMixin, viewsets.ModelViewSet):
    cache_resource     = "academic_reports"
    queryset           = AcademicReport.objects.none()
    permission_classes = [IsAuthenticated]
    pagination_class   = DynamicPageSizePagination
    filter_backends    = [filters.SearchFilter]
    search_fields      = ["teacher_comment", "head_teacher_comment", "student__first_name", "student__last_name"]

    def get_serializer_class(self):
        if self.action == 'list':
            return AcademicReportListSerializer
        return AcademicReportSerializer

    def _cache_discriminator(self, request) -> str:
        if is_parent(request.user):
            return f"parent:{request.user.id}"
        if is_pure_teacher(request.user):
            return f"teacher:{request.user.id}"
        return "admin_editor"

    def get_queryset(self):
        user = self.request.user
        qs   = AcademicReport.objects.select_related("student", "written_by", "term")

        if self.action in ['retrieve', 'create', 'update', 'partial_update']:
            qs = qs.prefetch_related("subject_scores")

        if is_parent(user):
            return qs.filter(student__parents=user, is_published=True).order_by('-id')

        if is_pure_teacher(user):
            qs = qs.filter(student__current_class__teacher=user)

        student      = self.request.query_params.get("student")
        term         = self.request.query_params.get("term")
        is_published = self.request.query_params.get("is_published")
        report_type  = self.request.query_params.get("report_type")
        classroom    = self.request.query_params.get("classroom")

        if student:      qs = qs.filter(student_id=student)
        if term:         qs = qs.filter(term_id=term)
        if report_type:  qs = qs.filter(report_type=report_type)
        if classroom:    qs = qs.filter(student__current_class_id=classroom)
        if is_published is not None:
            qs = qs.filter(is_published=is_published.lower() == "true")

        return qs.order_by('-id')

    def perform_create(self, serializer):
        # NOTE: must raise a DRF-recognized exception, not a bare PermissionError,
        # or this bubbles up as an unhandled 500 instead of a 403.
        if not is_staff(self.request.user):
            raise PermissionDenied("Staff access required.")
        serializer.save(written_by=self.request.user)

    def perform_update(self, serializer):
        # Parents can be granted read access to a published report (see
        # get_queryset), but that visibility must not translate into write
        # access. Only staff (admins/teachers) may edit a report.
        if not is_staff(self.request.user):
            raise PermissionDenied("Staff access required.")
        serializer.save()

    def destroy(self, request, *args, **kwargs):
        if not is_admin(request.user):
            return Response({"error": "Only admins can delete reports."}, status=403)
        return super().destroy(request, *args, **kwargs)

    @extend_schema(
        summary="Publish a report so parents can see it (Admin only)",
        request=None,
        responses={200: inline_serializer(
            name="PublishReportResponse",
            fields={"message": drf_serializers.CharField()}
        )}
    )
    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None):
        if not is_admin(request.user):
            return Response({"error": "Only admins can publish reports."}, status=403)

        report = self.get_object()
        if report.is_published:
            return Response({"message": "Already published."})

        report.is_published = True
        report.save(update_fields=["is_published"])
        self._bump()

        return Response({"message": f"Report for {report.student.full_name} is now visible to parents."})