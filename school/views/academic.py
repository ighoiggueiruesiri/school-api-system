from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter, OpenApiTypes, inline_serializer
from rest_framework import serializers as drf_serializers

from ..models import ClassRoom, Term, Student, Attendance, Assignment, AcademicReport
from ..serializers import (
    ClassRoomSerializer, TermSerializer, StudentSerializer,
    AttendanceSerializer, BulkAttendanceSerializer,
    AssignmentSerializer, AcademicReportSerializer, AcademicReportListSerializer
)
from .base import (
    DynamicPageSizePagination, VersionedCacheMixin,
    is_admin, is_admin_or_editor, is_parent, is_pure_teacher, is_staff
)

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
        user = self.request.user
        base_qs = ClassRoom.objects.annotate(
            student_count_annotated=Count(
                "students",
                filter=Q(students__is_active=True),
            )
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


@extend_schema(tags=["Academic Calendar Terms"])
@extend_schema_view(
    list=extend_schema(
        summary="List all academic terms",
        parameters=[OpenApiParameter(name="page_size", description="Results per page", required=False, type=OpenApiTypes.INT)]
    ),
    create=extend_schema(summary="Create an academic term (Admin or Editor)"),
    retrieve=extend_schema(summary="Retrieve a specific term"),
    update=extend_schema(summary="Update a term (Admin or Editor)"),
    partial_update=extend_schema(summary="Partially update a term (Admin or Editor)"),
    destroy=extend_schema(summary="Delete a term (Admin only)"),
)
class TermViewSet(VersionedCacheMixin, viewsets.ModelViewSet):
    cache_resource = "terms"

    def _cache_discriminator(self, request) -> str:
        return "all"
        
    queryset           = Term.objects.all().order_by('-id')
    serializer_class   = TermSerializer
    permission_classes = [IsAuthenticated]
    pagination_class   = DynamicPageSizePagination

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
            return Response({"error": "Only admins can delete terms."}, status=403)
        return super().destroy(request, *args, **kwargs)

    @extend_schema(summary="Get the active term", responses={200: TermSerializer})
    @action(detail=False, methods=["get"])
    def current(self, request):
        term = Term.objects.filter(is_current=True).first()
        if not term:
            return Response({"error": "No current term set."}, status=404)
        return Response(TermSerializer(term).data)


@extend_schema(tags=["Students Records Profile"])
@extend_schema_view(
    list=extend_schema(
        summary="List / filter student profiles",
        parameters=[
            OpenApiParameter(name="classroom", description="Filter by classroom ID", required=False, type=OpenApiTypes.INT),
            OpenApiParameter(name="page_size", description="Results per page", required=False, type=OpenApiTypes.INT),
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
            raise PermissionError("Admin or Editor access required.")
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
        absent  = agg["absent"]
        late    = agg["late"]

        return Response({
            "student":            student.full_name,
            "total_days":         total,
            "present":            present,
            "absent":             absent,
            "late":               late,
            "attendance_percent": round(present / total * 100, 1) if total else 0,
        })


@extend_schema(tags=["Attendance Records Book"])
@extend_schema_view(
    list=extend_schema(
        summary="List attendance records",
        parameters=[
            OpenApiParameter(name="term",    description="Filter by term ID",    required=False, type=OpenApiTypes.INT),
            OpenApiParameter(name="date",    description="Filter by date",        required=False, type=OpenApiTypes.STR),
            OpenApiParameter(name="student", description="Filter by student ID",  required=False, type=OpenApiTypes.STR),
            OpenApiParameter(name="page_size", description="Results per page",   required=False, type=OpenApiTypes.INT),
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


@extend_schema(tags=["Assignments"])
@extend_schema_view(
    list=extend_schema(
        summary="List assignments",
        parameters=[
            OpenApiParameter(name="term",      description="Filter by term ID",   required=False, type=OpenApiTypes.INT),
            OpenApiParameter(name="type",      description="homework|classwork|project", required=False, type=OpenApiTypes.STR),
            OpenApiParameter(name="page_size", description="Results per page",    required=False, type=OpenApiTypes.INT),
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
    
    # FIX: Corrected search fields to match the AcademicReport model exactly
    search_fields      = ["teacher_comment", "head_teacher_comment", "student__first_name", "student__last_name"]

    def get_serializer_class(self):
        """
        Dynamically return the list serializer for list views to optimize payload,
        and the full serializer (with subject scores and deep data) for creates/retrieves.
        """
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
        
        # Base query: Only select_related for the ForeignKey lookups needed by BOTH serializers
        qs = AcademicReport.objects.select_related("student", "written_by", "term")

        # Optimization: Only prefetch the heavy subject scores if we are requesting detailed views
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
        if not is_staff(self.request.user):
            raise PermissionError("Staff access required.")
        serializer.save(written_by=self.request.user)

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