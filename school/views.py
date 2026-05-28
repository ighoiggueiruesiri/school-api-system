"""school/views.py"""
import uuid
from django.db import transaction
from django.utils import timezone
from rest_framework import viewsets, status, generics, filters
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.tokens import RefreshToken
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter, OpenApiTypes, inline_serializer
from rest_framework import serializers as drf_serializers
from rest_framework.throttling import ScopedRateThrottle
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django.views.decorators.vary import vary_on_headers
from django.db import connection
from django.db.utils import OperationalError

from .models import (
    User, ClassRoom, Term, Student, Attendance,
    Invoice, Payment, Announcement, Assignment, DevelopmentReport, CreditNote
)
from .serializers import (
    LoginSerializer, RegisterSerializer, UserSerializer,
    ClassRoomSerializer, TermSerializer, StudentSerializer,
    AttendanceSerializer, BulkAttendanceSerializer,
    InvoiceSerializer, PaymentSerializer, CreditNoteSerializer,
    AnnouncementSerializer, AssignmentSerializer, DevelopmentReportSerializer
)

CACHE_TTL = 60 * 15

# ── PAGINATION ────────────────────────────────────────────────────────────────

class DynamicPageSizePagination(PageNumberPagination):
    """
    Supports ?page=N&page_size=N from the frontend.
    Returns { count, pages, next, previous, results } so the React
    pagination bar can display "1–10 of 47" without a second request.
    """
    page_size              = 10
    page_size_query_param  = "page_size"
    max_page_size          = 200

    def get_paginated_response(self, data):
        return Response({
            "count":    self.page.paginator.count,
            "pages":    self.page.paginator.num_pages,
            "next":     self.get_next_link(),
            "previous": self.get_previous_link(),
            "results":  data,
        })


# ── ROLE HELPERS ──────────────────────────────────────────────────────────────
#
#  is_admin          → only "admin"            (create/delete sensitive records)
#  is_admin_or_editor→ "admin" | "editor"      (create/edit records, no delete)
#  is_staff          → "admin"|"editor"|"teacher" (broad read/write access)
#  is_teacher        → alias for is_staff      (backward-compat name)
#  is_parent         → only "parent"
#
#  DELETE operations always require is_admin.
#  Editor sees the full dataset (not scoped to one classroom like a pure teacher).

def is_admin(user):           return user.role == "admin"
def is_editor(user):          return user.role == "editor"
def is_admin_or_editor(user): return user.role in ("admin", "editor")
def is_staff(user):           return user.role in ("admin", "editor", "teacher")
def is_teacher(user):         return is_staff(user)   # kept for backward compat
def is_parent(user):          return user.role == "parent"
def is_pure_teacher(user):    return user.role == "teacher"  # scoped-to-class checks


# ── AUTH ──────────────────────────────────────────────────────────────────────

@extend_schema(tags=["Authentication"])
class LoginView(TokenObtainPairView):
    """POST /api/login/ — returns access + refresh JWT tokens."""
    serializer_class   = LoginSerializer
    permission_classes = [AllowAny]
    throttle_classes   = [ScopedRateThrottle]
    throttle_scope     = 'auth'

@extend_schema(tags=["Authentication"])
class RegisterView(APIView):
    """POST /api/register/ — parent self-registration, no login needed."""
    permission_classes = [AllowAny]
    throttle_classes   = [ScopedRateThrottle]
    throttle_scope     = 'auth'

    @extend_schema(
        summary="Parent Self-Registration",
        request=RegisterSerializer,
        responses={201: inline_serializer(
            name="RegisterSuccessResponse",
            fields={"message": drf_serializers.CharField(), "email": drf_serializers.EmailField()}
        )}
    )
    def post(self, request):
        s = RegisterSerializer(data=request.data)
        if s.is_valid():
            user = s.save()
            return Response(
                {"message": "Account created. You can now log in.", "email": user.email},
                status=status.HTTP_201_CREATED
            )
        return Response(s.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(tags=["Authentication"])
class LogoutView(APIView):
    """POST /api/logout/ — blacklists the refresh token."""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Logout / Blacklist Token",
        request=inline_serializer(name="LogoutRequest", fields={"refresh": drf_serializers.CharField()}),
        responses={200: inline_serializer(name="LogoutResponse", fields={"message": drf_serializers.CharField()})}
    )
    def post(self, request):
        try:
            RefreshToken(request.data["refresh"]).blacklist()
            return Response({"message": "Logged out."})
        except Exception:
            return Response({"error": "Invalid token."}, status=400)


@extend_schema(tags=["Authentication"])
class MeView(APIView):
    """GET /api/me/ — returns the currently logged-in user's profile."""
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Retrieve logged-in user details", responses={200: UserSerializer})
    def get(self, request):
        return Response(UserSerializer(request.user, context={"request": request}).data)

    @extend_schema(summary="Partially update logged-in user profile", request=UserSerializer, responses={200: UserSerializer})
    def patch(self, request):
        s = UserSerializer(request.user, data=request.data, partial=True, context={"request": request})
        if s.is_valid():
            s.save()
            return Response(s.data)
        return Response(s.errors, status=400)


# ── USERS ─────────────────────────────────────────────────────────────────────

@extend_schema(tags=["User Management"])
@extend_schema_view(
    list=extend_schema(
        summary="List all users",
        parameters=[
            OpenApiParameter(name="role", description="Filter by role: admin | editor | teacher | parent", required=False, type=OpenApiTypes.STR),
            OpenApiParameter(name="page_size", description="Results per page (default 10, max 200)", required=False, type=OpenApiTypes.INT),
        ]
    ),
    retrieve=extend_schema(summary="Retrieve a specific user profile"),
    update=extend_schema(summary="Completely update a user account"),
    partial_update=extend_schema(summary="Partially update user details"),
    destroy=extend_schema(summary="Deactivate a user account (Admin only)"),
)
class UserViewSet(viewsets.ModelViewSet):
    """
    /api/users/
    - Admin creates admin/editor/teacher accounts here.
    - Parents register via /api/register/ instead.
    - Editor role: view + edit only; destroy is admin-only.
    """
    queryset           = User.objects.none()
    serializer_class   = UserSerializer
    permission_classes = [IsAuthenticated]
    pagination_class   = DynamicPageSizePagination
    filter_backends    = [filters.SearchFilter]
    search_fields      = ["first_name", "last_name", "email"]

    def get_queryset(self):
        qs   = User.objects.all()
        role = self.request.query_params.get("role")
        if role:
            qs = qs.filter(role=role)
        return qs.order_by('-id')

    @extend_schema(
        summary="Create an Admin, Editor, or Teacher account (Admin only)",
        request=inline_serializer(
            name="AdminCreateUserRequest",
            fields={
                "email":      drf_serializers.EmailField(),
                "first_name": drf_serializers.CharField(),
                "last_name":  drf_serializers.CharField(),
                "phone":      drf_serializers.CharField(required=False),
                "role":       drf_serializers.ChoiceField(choices=["admin", "editor", "teacher"]),
                "password":   drf_serializers.CharField(required=False),
            }
        ),
        responses={201: UserSerializer}
    )
    def create(self, request, *args, **kwargs):
        if not is_admin(request.user):
            return Response({"error": "Only admins can create user accounts."}, status=403)
        data     = request.data.copy()
        password = data.pop("password", "ChangeMe123")
        user     = User.objects.create_user(password=password, **data)
        return Response(UserSerializer(user).data, status=201)

    def destroy(self, request, *args, **kwargs):
        """Deactivate (soft-delete) a user account. Admin only."""
        if not is_admin(request.user):
            return Response({"error": "Only admins can deactivate accounts."}, status=403)
        obj           = self.get_object()
        obj.is_active = False
        obj.save(update_fields=["is_active"])
        return Response({"message": "User deactivated."})

    '''
    def destroy(self, request, *args, **kwargs):
        if not is_admin(request.user):
            return Response({"error": "Admin only."}, status=403)
        return super().destroy(request, *args, **kwargs)
    '''


# ── CLASSROOMS ────────────────────────────────────────────────────────────────

@extend_schema(tags=["Classrooms Management"])
@method_decorator(cache_page(CACHE_TTL), name='list')
@method_decorator(vary_on_headers("Authorization"), name='list')
@method_decorator(cache_page(CACHE_TTL), name='retrieve')
@method_decorator(vary_on_headers("Authorization"), name='retrieve')
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
class ClassRoomViewSet(viewsets.ModelViewSet):
    """
    /api/classrooms/
    - Admin/Editor: full read-write (no delete for editor)
    - Teacher: sees only their own classroom
    - Parent: sees all (read)
    """
    queryset           = ClassRoom.objects.none()
    serializer_class   = ClassRoomSerializer
    permission_classes = [IsAuthenticated]
    pagination_class   = DynamicPageSizePagination
    filter_backends    = [filters.SearchFilter]
    search_fields      = ["name", "teacher__first_name", "teacher__last_name"]

    def get_queryset(self):
        user = self.request.user
        # Pure teachers see only their assigned classroom
        if is_pure_teacher(user):
            return ClassRoom.objects.filter(teacher=user).order_by('-id')
        # Admin, editor, parent → all classrooms
        return ClassRoom.objects.all().order_by('-id')

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


# ── TERMS ─────────────────────────────────────────────────────────────────────

@extend_schema(tags=["Academic Calendar Terms"])
@method_decorator(cache_page(CACHE_TTL), name='list')
@method_decorator(vary_on_headers("Authorization"), name='list')
@method_decorator(cache_page(CACHE_TTL), name='retrieve')
@method_decorator(vary_on_headers("Authorization"), name='retrieve')
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
class TermViewSet(viewsets.ModelViewSet):
    """
    /api/terms/
    GET /api/terms/current/ — returns the active term.
    """
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


# ── STUDENTS ──────────────────────────────────────────────────────────────────

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
class StudentViewSet(viewsets.ModelViewSet):
    """
    /api/students/
    - Admin/Editor: see and manage all students
    - Teacher: sees only students in their classroom
    - Parent: sees only their own children
    """
    queryset           = Student.objects.none()
    serializer_class   = StudentSerializer
    permission_classes = [IsAuthenticated]
    pagination_class   = DynamicPageSizePagination
    filter_backends    = [filters.SearchFilter]
    search_fields      = ["first_name", "last_name", "admission_number"]

    def get_queryset(self):
        user = self.request.user
        qs   = Student.objects.select_related("current_class").filter(is_active=True)

        if is_parent(user):
            return qs.filter(parents=user).order_by('-id')

        # Pure teacher → only their classroom
        if is_pure_teacher(user):
            qs = qs.filter(current_class__teacher=user)

        # Admin / editor / teacher can also filter by classroom
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
        """Soft-delete only. Admin only."""
        if not is_admin(request.user):
            return Response({"error": "Only admins can deactivate students."}, status=403)
        obj           = self.get_object()
        obj.is_active = False
        obj.save()
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
        total   = qs.count()
        present = qs.filter(status="present").count()
        absent  = qs.filter(status="absent").count()
        late    = qs.filter(status="late").count()
        return Response({
            "student":            student.full_name,
            "total_days":         total,
            "present":            present,
            "absent":             absent,
            "late":               late,
            "attendance_percent": round(present / total * 100, 1) if total else 0,
        })


# ── ATTENDANCE ────────────────────────────────────────────────────────────────

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
class AttendanceViewSet(viewsets.ModelViewSet):
    """
    /api/attendance/
    POST /api/attendance/bulk/ — mark a whole class at once.
    """
    queryset           = Attendance.objects.none()
    serializer_class   = AttendanceSerializer
    permission_classes = [IsAuthenticated]
    pagination_class   = DynamicPageSizePagination
    filter_backends    = [filters.SearchFilter]
    search_fields      = ["reason", "student__first_name", "student__last_name"]

    def get_queryset(self):
        user    = self.request.user
        qs      = Attendance.objects.select_related("student", "recorded_by")
        term_id = self.request.query_params.get("term")
        date    = self.request.query_params.get("date")
        student = self.request.query_params.get("student")

        if is_parent(user):
            qs = qs.filter(student__parents=user)
        elif is_pure_teacher(user):
            # Pure teachers only see their classroom's attendance
            qs = qs.filter(student__current_class__teacher=user)
        # Admin and editor see all records

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
        """
        POST /api/attendance/bulk/
        Body: { "date": "2025-09-15", "term": 1, "records": [
                  {"student_id": "...", "status": "present"},
                  {"student_id": "...", "status": "absent", "reason": "sick"}
                ]}
        """
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

        with transaction.atomic():
            for r in records:
                try:
                    student = Student.objects.get(id=r["student_id"])
                    _, made = Attendance.objects.update_or_create(
                        student=student, date=date,
                        defaults={
                            "status":      r.get("status", "present"),
                            "reason":      r.get("reason", ""),
                            "term":        term,
                            "recorded_by": request.user,
                        }
                    )
                    if made: created += 1
                    else:    updated += 1
                except Student.DoesNotExist:
                    errors.append(f"Student {r.get('student_id')} not found")

        return Response({
            "created": created,
            "updated": updated,
            "errors":  errors,
            "message": f"Attendance saved for {created + updated} students.",
        })


# ── FINANCE ───────────────────────────────────────────────────────────────────

@extend_schema(tags=["Financial Invoices Accounting"])
@extend_schema_view(
    list=extend_schema(
        summary="List invoices",
        parameters=[
            OpenApiParameter(name="student",   description="Filter by student ID",  required=False, type=OpenApiTypes.STR),
            OpenApiParameter(name="term",      description="Filter by term ID",     required=False, type=OpenApiTypes.INT),
            OpenApiParameter(name="status",    description="unpaid | partial | paid", required=False, type=OpenApiTypes.STR),
            OpenApiParameter(name="page_size", description="Results per page",      required=False, type=OpenApiTypes.INT),
        ]
    ),
    create=extend_schema(summary="Generate an invoice (Admin or Editor)"),
    destroy=extend_schema(summary="Delete an invoice (Admin only)"),
)
class InvoiceViewSet(viewsets.ModelViewSet):
    """
    /api/invoices/
    Admin/Editor creates invoices. Parents see their children's invoices.
    """
    queryset           = Invoice.objects.none()
    serializer_class   = InvoiceSerializer
    permission_classes = [IsAuthenticated]
    pagination_class   = DynamicPageSizePagination
    filter_backends    = [filters.SearchFilter]
    search_fields      = ["invoice_number", "description", "student__first_name", "student__last_name"]

    def get_queryset(self):
        user = self.request.user
        qs   = Invoice.objects.select_related("student", "term").prefetch_related("payments")
        if is_parent(user):
            qs = qs.filter(student__parents=user)
        student = self.request.query_params.get("student")
        term    = self.request.query_params.get("term")
        status  = self.request.query_params.get("status")
        if student: qs = qs.filter(student_id=student)
        if term:    qs = qs.filter(term_id=term)
        if status:  qs = qs.filter(status=status)
        return qs.order_by('-id')

    def perform_create(self, serializer):
        if not is_admin_or_editor(self.request.user):
            raise PermissionError("Admin or Editor access required.")
        student   = serializer.validated_data["student"]
        term      = serializer.validated_data["term"]
        short_uuid = uuid.uuid4().hex[:6].upper()
        num       = f"INV-{student.admission_number}-{term.id}-{short_uuid}"
        serializer.save(invoice_number=num)

    def destroy(self, request, *args, **kwargs):
        if not is_admin(request.user):
            return Response({"error": "Only admins can delete invoices."}, status=403)
        return super().destroy(request, *args, **kwargs)

    @extend_schema(
        summary="Financial totals summary",
        parameters=[OpenApiParameter(name="student", description="Student ID", required=False, type=OpenApiTypes.STR)],
        responses={200: inline_serializer(
            name="InvoiceSummaryResponse",
            fields={
                "total_billed":  drf_serializers.FloatField(),
                "total_paid":    drf_serializers.FloatField(),
                "balance":       drf_serializers.FloatField(),
                "invoice_count": drf_serializers.IntegerField(),
                "unpaid_count":  drf_serializers.IntegerField(),
            }
        )}
    )
    @action(detail=False, methods=["get"])
    def summary(self, request):
        """GET /api/invoices/summary/?student=<id>"""
        from django.db.models import Sum
        qs         = self.get_queryset()
        student_id = request.query_params.get("student")
        if student_id:
            qs = qs.filter(student_id=student_id)
        totals = qs.aggregate(billed=Sum("amount"), paid=Sum("amount_paid"))
        billed = totals["billed"] or 0
        paid   = totals["paid"]   or 0
        return Response({
            "total_billed":  billed,
            "total_paid":    paid,
            "balance":       billed - paid,
            "invoice_count": qs.count(),
            "unpaid_count":  qs.filter(status__in=["unpaid", "partial"]).count(),
        })


@extend_schema(tags=["Financial Payments Records Processing"])
@extend_schema_view(
    list=extend_schema(
        summary="List payment records",
        parameters=[
            OpenApiParameter(name="invoice",   description="Filter by invoice ID", required=False, type=OpenApiTypes.STR),
            OpenApiParameter(name="page_size", description="Results per page",     required=False, type=OpenApiTypes.INT),
        ]
    ),
    create=extend_schema(summary="Record a payment (Admin or Editor)"),
    destroy=extend_schema(summary="Delete a payment record (Admin only)"),
)
class PaymentViewSet(viewsets.ModelViewSet):
    """
    /api/payments/
    Admin/Editor records cash / bank transfer / POS payments manually.
    """
    queryset           = Payment.objects.none()
    serializer_class   = PaymentSerializer
    permission_classes = [IsAuthenticated]
    pagination_class   = DynamicPageSizePagination
    filter_backends    = [filters.SearchFilter]
    search_fields      = ["reference", "notes", "invoice__invoice_number"]

    def get_queryset(self):
        qs = Payment.objects.select_related("invoice__student")
        if is_parent(self.request.user):
            qs = qs.filter(invoice__student__parents=self.request.user)
        invoice = self.request.query_params.get("invoice")
        if invoice:
            qs = qs.filter(invoice_id=invoice)
        return qs.order_by('-id')

    def perform_create(self, serializer):
        if not is_admin_or_editor(self.request.user):
            raise PermissionError("Admin or Editor access required.")
        serializer.save(paid_by=self.request.user)

    def destroy(self, request, *args, **kwargs):
        if not is_admin(request.user):
            return Response({"error": "Only admins can delete payment records."}, status=403)
        return super().destroy(request, *args, **kwargs)


@extend_schema(tags=["Financial Credit Notes Processing"])
@extend_schema_view(
    list=extend_schema(
        summary="List credit notes",
        parameters=[
            OpenApiParameter(name="student",   description="Filter by student ID", required=False, type=OpenApiTypes.STR),
            OpenApiParameter(name="page_size", description="Results per page",     required=False, type=OpenApiTypes.INT),
        ]
    ),
    create=extend_schema(summary="Log a credit note (Admin or Editor)"),
    destroy=extend_schema(summary="Delete a credit note (Admin only)"),
)
class CreditNoteViewSet(viewsets.ModelViewSet):
    """
    /api/credit-notes/
    Admin/Editor records parent overpayments manually.
    """
    queryset           = CreditNote.objects.none()
    serializer_class   = CreditNoteSerializer
    permission_classes = [IsAuthenticated]
    pagination_class   = DynamicPageSizePagination
    filter_backends    = [filters.SearchFilter]
    search_fields      = ["reference", "notes", "student__first_name", "student__last_name"]

    def get_queryset(self):
        user = self.request.user
        qs   = CreditNote.objects.select_related("student", "logged_by")
        if is_parent(user):
            return qs.filter(student__parents=user)
        student = self.request.query_params.get("student")
        if student:
            qs = qs.filter(student_id=student)
        return qs.order_by('-id')

    def perform_create(self, serializer):
        if not is_admin_or_editor(self.request.user):
            raise PermissionError("Admin or Editor access required.")
        serializer.save(logged_by=self.request.user)

    def destroy(self, request, *args, **kwargs):
        if not is_admin(request.user):
            return Response({"error": "Only admins can delete credit notes."}, status=403)
        return super().destroy(request, *args, **kwargs)


# ── ANNOUNCEMENTS ─────────────────────────────────────────────────────────────

@extend_schema(tags=["Announcements"])
@method_decorator(cache_page(CACHE_TTL), name='list')
@method_decorator(vary_on_headers("Authorization"), name='list')
@method_decorator(cache_page(CACHE_TTL), name='retrieve')
@method_decorator(vary_on_headers("Authorization"), name='retrieve')
@extend_schema_view(
    list=extend_schema(
        summary="List announcements",
        parameters=[OpenApiParameter(name="page_size", description="Results per page", required=False, type=OpenApiTypes.INT)]
    ),
    create=extend_schema(summary="Post an announcement (Staff only)"),
    destroy=extend_schema(summary="Delete an announcement (Admin only)"),
)
class AnnouncementViewSet(viewsets.ModelViewSet):
    """
    /api/announcements/
    Staff posts. All users read. Only admin deletes.
    """
    queryset           = Announcement.objects.none()
    serializer_class   = AnnouncementSerializer
    permission_classes = [IsAuthenticated]
    pagination_class   = DynamicPageSizePagination
    filter_backends    = [filters.SearchFilter]
    search_fields      = ["title", "body"]

    def get_queryset(self):
        user = self.request.user
        qs   = Announcement.objects.all()
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


# ── ASSIGNMENTS ───────────────────────────────────────────────────────────────

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
class AssignmentViewSet(viewsets.ModelViewSet):
    """
    /api/assignments/
    Staff creates. Parents see their child's class assignments.
    """
    queryset           = Assignment.objects.none()
    serializer_class   = AssignmentSerializer
    permission_classes = [IsAuthenticated]
    pagination_class   = DynamicPageSizePagination
    filter_backends    = [filters.SearchFilter]
    search_fields      = ["title", "description"]

    def get_queryset(self):
        user = self.request.user
        qs   = Assignment.objects.select_related("classroom", "teacher")

        if is_parent(user):
            classes = Student.objects.filter(
                parents=user, is_active=True
            ).values_list("current_class_id", flat=True)
            return qs.filter(classroom_id__in=classes).order_by('-id')

        # Pure teacher → only their own assignments
        if is_pure_teacher(user):
            return qs.filter(teacher=user).order_by('-id')

        # Admin / editor → all, with optional filters
        term = self.request.query_params.get("term")
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


# ── DEVELOPMENT REPORTS ───────────────────────────────────────────────────────

@extend_schema(tags=["Development Reports"])
@extend_schema_view(
    list=extend_schema(
        summary="List development reports",
        parameters=[
            OpenApiParameter(name="student",      description="Filter by student ID",    required=False, type=OpenApiTypes.STR),
            OpenApiParameter(name="term",         description="Filter by term ID",       required=False, type=OpenApiTypes.INT),
            OpenApiParameter(name="is_published", description="true | false",            required=False, type=OpenApiTypes.BOOL),
            OpenApiParameter(name="page_size",    description="Results per page",        required=False, type=OpenApiTypes.INT),
        ]
    ),
    create=extend_schema(summary="Write a development report (Staff only)"),
    destroy=extend_schema(summary="Delete a report (Admin only)"),
)
class DevelopmentReportViewSet(viewsets.ModelViewSet):
    """
    /api/reports/
    Staff writes. Parent reads published reports for their children only.
    POST /api/reports/<id>/publish/ — admin publishes to parents.
    """
    queryset           = DevelopmentReport.objects.none()
    serializer_class   = DevelopmentReportSerializer
    permission_classes = [IsAuthenticated]
    pagination_class   = DynamicPageSizePagination
    filter_backends    = [filters.SearchFilter]
    search_fields      = ["comment", "strengths", "areas_to_improve", "student__first_name", "student__last_name"]

    def get_queryset(self):
        user = self.request.user
        qs   = DevelopmentReport.objects.select_related("student", "written_by", "term")

        if is_parent(user):
            return qs.filter(student__parents=user, is_published=True).order_by('-id')

        # Pure teacher → only reports for their classroom
        if is_pure_teacher(user):
            qs = qs.filter(student__current_class__teacher=user)

        # Admin / editor → all reports, with optional filters
        student      = self.request.query_params.get("student")
        term         = self.request.query_params.get("term")
        is_published = self.request.query_params.get("is_published")
        if student:      qs = qs.filter(student_id=student)
        if term:         qs = qs.filter(term_id=term)
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
        """POST /api/reports/<id>/publish/"""
        if not is_admin(request.user):
            return Response({"error": "Only admins can publish reports."}, status=403)
        report = self.get_object()
        if report.is_published:
            return Response({"message": "Already published."})
        report.is_published = True
        report.save(update_fields=["is_published"])
        return Response({"message": f"Report for {report.student.full_name} is now visible to parents."})


# ── SYSTEM ────────────────────────────────────────────────────────────────────
@extend_schema(tags=["System"])
class HealthCheckView(APIView):
    """GET /api — Checks API availability and Database connection."""
    permission_classes = [AllowAny]
    
    @extend_schema(
        summary="System Health Check",
        responses={
            200: inline_serializer(
                name="HealthCheckSuccess",
                fields={
                    "status": drf_serializers.CharField(default="healthy"),
                    "database": drf_serializers.CharField(default="connected"),
                    "timestamp": drf_serializers.DateTimeField()
                }
            ),
            503: inline_serializer(
                name="HealthCheckFail",
                fields={
                    "status": drf_serializers.CharField(default="unhealthy"),
                    "database": drf_serializers.CharField(default="disconnected"),
                    "error": drf_serializers.CharField()
                }
            )
        }
    )
    def get(self, request):
        try:
            # Explicitly force a database call to verify Postgres is alive
            connection.ensure_connection()
            return Response({
                "status": "healthy",
                "database": "connected",
                "timestamp": timezone.now()
            }, status=status.HTTP_200_OK)
            
        except OperationalError as e:
            return Response({
                "status": "unhealthy",
                "database": "disconnected",
                "error": str(e)
            }, status=status.HTTP_503_SERVICE_UNAVAILABLE)