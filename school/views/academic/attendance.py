from django.db import transaction
from rest_framework import viewsets, filters
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter, OpenApiTypes, inline_serializer
from rest_framework import serializers as drf_serializers

from ...models import Attendance, Student
from ...serializers import AttendanceSerializer, BulkAttendanceSerializer
from ..base import (
    DynamicPageSizePagination, VersionedCacheMixin,
    is_admin, is_parent, is_pure_teacher, is_staff,
)


@extend_schema(tags=["Attendance Records Book"])
@extend_schema_view(
    list=extend_schema(
        summary="List attendance records",
        parameters=[
            OpenApiParameter(name="term",      description="Filter by term ID",    required=False, type=OpenApiTypes.INT),
            OpenApiParameter(name="date",      description="Filter by date",        required=False, type=OpenApiTypes.STR),
            OpenApiParameter(name="student",   description="Filter by student ID",  required=False, type=OpenApiTypes.STR),
            OpenApiParameter(name="page_size", description="Results per page",      required=False, type=OpenApiTypes.INT),
        ]
    ),
    create=extend_schema(summary="Create a single attendance record"),
    destroy=extend_schema(summary="Delete an attendance record (Admin only)"),
)
class AttendanceViewSet(VersionedCacheMixin, viewsets.ModelViewSet):
    cache_resource     = "attendance"
    queryset           = Attendance.objects.none()
    serializer_class   = AttendanceSerializer
    permission_classes = [IsAuthenticated]
    pagination_class   = DynamicPageSizePagination
    filter_backends    = [filters.SearchFilter]
    search_fields      = ["reason", "student__first_name", "student__last_name"]

    def _cache_discriminator(self, request) -> str:
        if is_parent(request.user):
            return f"parent:{request.user.id}"
        if is_pure_teacher(request.user):
            return f"teacher:{request.user.id}"
        return "admin_editor"

    def get_queryset(self):
        user    = self.request.user
        qs      = Attendance.objects.select_related("student", "recorded_by")
        term_id = self.request.query_params.get("term")
        date    = self.request.query_params.get("date")
        student = self.request.query_params.get("student")

        if is_parent(user):
            qs = qs.filter(student__parents=user)
        elif is_pure_teacher(user):
            qs = qs.filter(student__current_class__teacher=user)

        if term_id: qs = qs.filter(term_id=term_id)
        if date:    qs = qs.filter(date=date)
        if student: qs = qs.filter(student_id=student)
        return qs.order_by('-id')

    def perform_create(self, serializer):
        serializer.save(recorded_by=self.request.user)

    def destroy(self, request, *args, **kwargs):
        if not is_admin(request.user):
            return Response({"error": "Only admins can delete attendance records."}, status=403)
        return super().destroy(request, *args, **kwargs)

    @extend_schema(
        summary="Bulk mark attendance for a whole class (Staff only)",
        request=BulkAttendanceSerializer,
        responses={200: inline_serializer(
            name="BulkAttendanceResponse",
            fields={
                "created": drf_serializers.IntegerField(),
                "updated": drf_serializers.IntegerField(),
                "errors":  drf_serializers.ListField(child=drf_serializers.CharField()),
                "message": drf_serializers.CharField(),
            }
        )}
    )
    @action(detail=False, methods=["post"])
    def bulk(self, request):
        if not is_staff(request.user):
            return Response({"error": "Staff access required."}, status=403)

        s = BulkAttendanceSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        date, term, records = (
            s.validated_data["date"],
            s.validated_data["term"],
            s.validated_data["records"],
        )
        created = updated = 0
        errors  = []

        student_ids = [r.get("student_id") for r in records if r.get("student_id")]
        student_map = {
            str(s_obj.id): s_obj
            for s_obj in Student.objects.filter(id__in=student_ids)
        }

        with transaction.atomic():
            for r in records:
                sid     = str(r.get("student_id", ""))
                student = student_map.get(sid)
                if not student:
                    errors.append(f"Student {r.get('student_id')} not found")
                    continue
                try:
                    _, made = Attendance.objects.update_or_create(
                        student=student, date=date,
                        defaults={
                            "status":      r.get("status", "present"),
                            "reason":      r.get("reason", ""),
                            "outlook":     r.get("outlook", ""),
                            "term":        term,
                            "recorded_by": request.user,
                        }
                    )
                    if made: created += 1
                    else:    updated += 1
                except Exception as exc:
                    errors.append(f"Student {sid}: {exc}")

        if created + updated > 0:
            self._bump()

        return Response({
            "created": created,
            "updated": updated,
            "errors":  errors,
            "message": f"Attendance saved for {created + updated} students.",
        })
