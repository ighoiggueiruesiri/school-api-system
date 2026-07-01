from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import viewsets, filters
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter, OpenApiTypes, inline_serializer
from rest_framework import serializers as drf_serializers

from ...models import Student
from ...serializers import StudentSerializer
from ..base import (
    DynamicPageSizePagination, VersionedCacheMixin,
    is_admin, is_admin_or_editor, is_parent, is_pure_teacher,
)


@extend_schema(tags=["Students Records Profile"])
@extend_schema_view(
    list=extend_schema(
        summary="List / filter student profiles",
        parameters=[
            OpenApiParameter(name="classroom", description="Filter by classroom ID", required=False, type=OpenApiTypes.INT),
            OpenApiParameter(name="page_size", description="Results per page",       required=False, type=OpenApiTypes.INT),
        ]
    ),
    create=extend_schema(summary="Enrol a new student (Admin or Editor)"),
    retrieve=extend_schema(summary="Get a student's profile"),
    update=extend_schema(summary="Update a student profile (Admin or Editor)"),
    partial_update=extend_schema(summary="Partially update a student (Admin or Editor)"),
    destroy=extend_schema(summary="Soft-deactivate a student (Admin only)"),
)
class StudentViewSet(VersionedCacheMixin, viewsets.ModelViewSet):
    cache_resource     = "students"
    queryset           = Student.objects.none()
    serializer_class   = StudentSerializer
    permission_classes = [IsAuthenticated]
    pagination_class   = DynamicPageSizePagination
    filter_backends    = [filters.SearchFilter]
    search_fields      = ["first_name", "last_name", "admission_number"]

    def _cache_discriminator(self, request) -> str:
        if is_parent(request.user):
            return f"parent:{request.user.id}"
        if is_pure_teacher(request.user):
            return f"teacher:{request.user.id}"
        return "admin_editor"

    def get_queryset(self):
        user = self.request.user
        qs   = Student.objects.select_related("current_class").filter(is_active=True)

        if is_parent(user):
            return qs.filter(parents=user).order_by('-id')

        if is_pure_teacher(user):
            qs = qs.filter(current_class__teacher=user)

        classroom = self.request.query_params.get("classroom")
        if classroom:
            qs = qs.filter(current_class_id=classroom)

        return qs.order_by('-id')

    def perform_create(self, serializer):
        if not is_admin_or_editor(self.request.user):
            # Use DRF's PermissionDenied so this surfaces as a 403 through
            # the standard exception handler, instead of an unhandled
            # PermissionError that DRF doesn't know how to catch (500).
            raise PermissionDenied("Admin or Editor access required.")
        year  = timezone.now().year
        count = Student.objects.filter(admission_date__year=year).count() + 1
        serializer.save(admission_number=f"GSA-{year}-{count:04d}")

    def update(self, request, *args, **kwargs):
        if not is_admin_or_editor(request.user):
            return Response({"error": "Admin or Editor access required."}, status=403)
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        if not is_admin(request.user):
            return Response({"error": "Only admins can deactivate students."}, status=403)
        obj           = self.get_object()
        obj.is_active = False
        obj.save()
        self._bump()
        return Response({"message": "Student deactivated."})

    @extend_schema(summary="Get the parent's own children", responses={200: StudentSerializer(many=True)})
    @action(detail=False, methods=["get"])
    def mine(self, request):
        students = Student.objects.filter(parents=request.user, is_active=True)
        return Response(StudentSerializer(students, many=True, context={"request": request}).data)

    @extend_schema(
        summary="Attendance summary for a student",
        parameters=[OpenApiParameter(name="term", description="Term ID", required=False, type=OpenApiTypes.INT)],
        responses={200: inline_serializer(
            name="AttendanceSummaryResponse",
            fields={
                "student":            drf_serializers.CharField(),
                "total_days":         drf_serializers.IntegerField(),
                "present":            drf_serializers.IntegerField(),
                "absent":             drf_serializers.IntegerField(),
                "late":               drf_serializers.IntegerField(),
                "attendance_percent": drf_serializers.FloatField(),
            }
        )}
    )
    @action(detail=True, methods=["get"], url_path="attendance-summary")
    def attendance_summary(self, request, pk=None):
        student = self.get_object()
        term_id = request.query_params.get("term")
        qs      = student.attendance.all()
        if term_id:
            qs = qs.filter(term_id=term_id)

        agg = qs.aggregate(
            total=Count("id"),
            present=Count("id", filter=Q(status="present")),
            absent=Count("id",  filter=Q(status="absent")),
            late=Count("id",    filter=Q(status="late")),
        )
        total   = agg["total"]
        present = agg["present"]

        return Response({
            "student":            student.full_name,
            "total_days":         total,
            "present":            present,
            "absent":             agg["absent"],
            "late":               agg["late"],
            "attendance_percent": round(present / total * 100, 1) if total else 0,
        })