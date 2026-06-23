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
from django.core.cache import cache
from django.db import connection
from django.db.utils import OperationalError
from .cache_utils import bump_cache_version, make_cache_key, CACHE_TTL

from .models import (
    User, ClassRoom, Term, Student, Attendance,
    Invoice, Payment, Announcement, Assignment, DevelopmentReport, CreditNote, AuditLog,
    Inquiry, Expenditure,  
)
from .serializers import (
    LoginSerializer, RegisterSerializer, UserSerializer,
    ClassRoomSerializer, TermSerializer, StudentSerializer,
    AttendanceSerializer, BulkAttendanceSerializer,
    InvoiceSerializer, PaymentSerializer, CreditNoteSerializer,
    AnnouncementSerializer, AssignmentSerializer, DevelopmentReportSerializer, AuditLogSerializer,
    InquirySerializer, ExpenditureSerializer,
)

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


# ── CACHE VERSIONING MIXIN ────────────────────────────────────────────────────
#
# Drop-in mixin for ModelViewSet.  Replaces @cache_page with a version-counter
# strategy so that any write (create / update / destroy) immediately invalidates
# the cached reads for that resource — without needing signals or complex key
# deletion logic.
#
# How to use
# ──────────
#   class MyViewSet(VersionedCacheMixin, viewsets.ModelViewSet):
#       cache_resource = "my_resource"          # unique string for this resource
#
#       # Optional: override _cache_discriminator to scope by user identity.
#       # Default scopes by role (parent vs non-parent), which is sufficient
#       # for most endpoints.  For teacher-scoped data, return the user's id.
#
# Read path  → list() / retrieve() check the versioned key; serve from cache
#              on hit, populate it on miss.
# Write path → create() / update() / partial_update() / destroy() delegate to
#              super() first; if the response is a success, bump the version.
#              This makes every existing cached key for the resource stale
#              in O(1) without touching each individual entry.

class VersionedCacheMixin:
    """Versioned read-cache + automatic invalidation on writes."""

    cache_resource: str = ""   # subclass must set this

    # ── Key helpers ───────────────────────────────────────────────────────────

    def _cache_discriminator(self, request) -> str:
        """
        Return a string that distinguishes what a user is allowed to see.

        Default: user role — parent-role users have filtered querysets on some
        endpoints (announcements filtered by audience, classrooms filtered by
        teacher assignment…) so their cache must not bleed into staff cache.

        Subclasses override this to add finer granularity (e.g. teacher user id).
        """
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
def is_staff(user):           return user.role in ("admin", "editor", "teacher", "non_academic")
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
            OpenApiParameter(name="role", description="Filter by role: admin | editor | teacher | non_academic | parent", required=False, type=OpenApiTypes.STR),
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
    - Admin creates admin/editor/teacher/non_academic accounts here.
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
        summary="Create an Admin, Editor, Teacher, or Non-Academic account (Admin only)",
        request=inline_serializer(
            name="AdminCreateUserRequest",
            fields={
                "email":      drf_serializers.EmailField(),
                "first_name": drf_serializers.CharField(),
                "last_name":  drf_serializers.CharField(),
                "phone":      drf_serializers.CharField(required=False),
                "role":       drf_serializers.ChoiceField(choices=["admin", "editor", "teacher", "non_academic"]),
                "password":   drf_serializers.CharField(required=False),
                "staff_profile": drf_serializers.DictField(required=False, help_text="Nested HR data for staff")
            }
        ),
        responses={201: UserSerializer}
    )
    def create(self, request, *args, **kwargs):
        if not is_admin(request.user):
            return Response({"error": "Only admins can create user accounts."}, status=403)
        
        # 1. Copy the incoming data so we can modify it
        data = request.data.copy()
        
        # 2. Extract and remove specific fields before passing to the User creator
        password = data.pop("password", "ChangeMe123")
        profile_data = data.pop("staff_profile", None) 
        
        # 3. Create the base User (Authentication layer)
        user = User.objects.create_user(password=password, **data)

        # 4. If this user is a staff member AND we received HR data, create the profile
        if profile_data and user.role in ["teacher", "non_academic"]:
            from .models import StaffProfile
            StaffProfile.objects.create(user=user, **profile_data)

        # 5. Return the fully nested representation
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
    """
    /api/classrooms/
    - Admin/Editor: full read-write (no delete for editor)
    - Teacher: sees only their own classroom
    - Parent: sees all (read)
    """
    cache_resource     = "classrooms"
    queryset           = ClassRoom.objects.none()
    serializer_class   = ClassRoomSerializer
    permission_classes = [IsAuthenticated]
    pagination_class   = DynamicPageSizePagination
    filter_backends    = [filters.SearchFilter]
    search_fields      = ["name", "teacher__first_name", "teacher__last_name"]

    def _cache_discriminator(self, request) -> str:
        # Pure teachers see only their own classroom — scope by user id.
        # Everyone else (admin / editor / parent) sees the full list.
        if is_pure_teacher(request.user):
            return f"teacher:{request.user.id}"
        return "all"

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
        return super().create(request, *args, **kwargs)  # mixin bumps cache on 201

    def update(self, request, *args, **kwargs):
        if not is_admin_or_editor(request.user):
            return Response({"error": "Admin or Editor access required."}, status=403)
        return super().update(request, *args, **kwargs)  # mixin bumps cache on 200

    def destroy(self, request, *args, **kwargs):
        if not is_admin(request.user):
            return Response({"error": "Only admins can delete classrooms."}, status=403)
        return super().destroy(request, *args, **kwargs)  # mixin bumps cache on 204


# ── TERMS ─────────────────────────────────────────────────────────────────────

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
    """
    /api/terms/
    GET /api/terms/current/ — returns the active term.
    """
    cache_resource = "terms"
    # All authenticated users see the same term list — no role-scoping needed.
    # The default _cache_discriminator (by role) is intentionally overridden
    # here to use a single shared cache entry per query string, regardless of role.
    def _cache_discriminator(self, request) -> str:
        return "all"
    queryset           = Term.objects.all().order_by('-id')
    serializer_class   = TermSerializer
    permission_classes = [IsAuthenticated]
    pagination_class   = DynamicPageSizePagination

    def create(self, request, *args, **kwargs):
        if not is_admin_or_editor(request.user):
            return Response({"error": "Admin or Editor access required."}, status=403)
        return super().create(request, *args, **kwargs)  # mixin bumps cache on 201

    def update(self, request, *args, **kwargs):
        if not is_admin_or_editor(request.user):
            return Response({"error": "Admin or Editor access required."}, status=403)
        return super().update(request, *args, **kwargs)  # mixin bumps cache on 200

    def destroy(self, request, *args, **kwargs):
        if not is_admin(request.user):
            return Response({"error": "Only admins can delete terms."}, status=403)
        return super().destroy(request, *args, **kwargs)  # mixin bumps cache on 204

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
class StudentViewSet(VersionedCacheMixin, viewsets.ModelViewSet):
    """
    /api/students/
    - Admin/Editor: see and manage all students
    - Teacher: sees only students in their classroom
    - Parent: sees only their own children
    """
    cache_resource     = "students"
    queryset           = Student.objects.none()
    serializer_class   = StudentSerializer
    permission_classes = [IsAuthenticated]
    pagination_class   = DynamicPageSizePagination
    filter_backends    = [filters.SearchFilter]
    search_fields      = ["first_name", "last_name", "admission_number"]

    def _cache_discriminator(self, request) -> str:
        # Each parent sees only their own children → scope to user id.
        # Each teacher sees only their classroom → scope to user id.
        # Admin / editor share the full unfiltered dataset.
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
        return super().update(request, *args, **kwargs)  # mixin bumps cache on 200

    def destroy(self, request, *args, **kwargs):
        """
        Soft-delete only. Admin only.
        This method performs a manual save() and returns a custom 200 response
        instead of the standard 204 — so the mixin cannot detect it automatically.
        We call self._bump() explicitly after the save.
        """
        if not is_admin(request.user):
            return Response({"error": "Only admins can deactivate students."}, status=403)
        obj           = self.get_object()
        obj.is_active = False
        obj.save()
        self._bump()   # invalidate cache — the student has disappeared from active lists
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
class AttendanceViewSet(VersionedCacheMixin, viewsets.ModelViewSet):
    """
    /api/attendance/
    POST /api/attendance/bulk/ — mark a whole class at once.
    """
    cache_resource     = "attendance"
    queryset           = Attendance.objects.none()
    serializer_class   = AttendanceSerializer
    permission_classes = [IsAuthenticated]
    pagination_class   = DynamicPageSizePagination
    filter_backends    = [filters.SearchFilter]
    search_fields      = ["reason", "student__first_name", "student__last_name"]

    def _cache_discriminator(self, request) -> str:
        # Attendance is scoped identically to students:
        # parent → their children only, teacher → their classroom only.
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
                  {"student_id": "...", "status": "present", "outlook": "Happy/Energetic"},
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
                            "outlook":     r.get("outlook", ""),
                            "term":        term,
                            "recorded_by": request.user,
                        }
                    )
                    if made: created += 1
                    else:    updated += 1
                except Student.DoesNotExist:
                    errors.append(f"Student {r.get('student_id')} not found")

        # bulk() writes via update_or_create — the mixin's create/update hooks
        # cannot intercept @action methods.  Bump explicitly so the attendance
        # list cache is invalidated for all roles immediately after this call.
        if created + updated > 0:
            self._bump()

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
class InvoiceViewSet(VersionedCacheMixin, viewsets.ModelViewSet):
    """
    /api/invoices/
    Admin/Editor creates invoices. Parents see their children's invoices.
    """
    cache_resource     = "invoices"
    queryset           = Invoice.objects.none()
    serializer_class   = InvoiceSerializer
    permission_classes = [IsAuthenticated]
    pagination_class   = DynamicPageSizePagination
    filter_backends    = [filters.SearchFilter]
    search_fields      = ["invoice_number", "description", "student__first_name", "student__last_name"]

    def _cache_discriminator(self, request) -> str:
        # Parents see only their children's invoices — scope by user id.
        # Admin / editor share the full dataset (further narrowed by query params,
        # which are already baked into the cache key via the query string).
        if is_parent(request.user):
            return f"parent:{request.user.id}"
        return "admin_editor"

    def get_queryset(self):
        user = self.request.user
        #qs   = Invoice.objects.select_related("student", "term").prefetch_related("payments")
        qs = Invoice.objects.select_related("student", "term").prefetch_related("payments", "line_items")
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

# ── EXPENDITURES ──────────────────────────────────────────────────────────────
 
@extend_schema(tags=["Financial Expenditures"])
@extend_schema_view(
    list=extend_schema(
        summary="List expenditures",
        parameters=[
            OpenApiParameter(name="category",  description="Filter by category slug", required=False, type=OpenApiTypes.STR),
            OpenApiParameter(name="date_from", description="YYYY-MM-DD start date",   required=False, type=OpenApiTypes.DATE),
            OpenApiParameter(name="date_to",   description="YYYY-MM-DD end date",     required=False, type=OpenApiTypes.DATE),
            OpenApiParameter(name="page_size", description="Results per page",        required=False, type=OpenApiTypes.INT),
        ]
    ),
    create=extend_schema(summary="Record an expenditure (Admin or Editor)"),
    destroy=extend_schema(summary="Delete an expenditure record (Admin only)"),
)
class ExpenditureViewSet(viewsets.ModelViewSet):
    """
    /api/expenditures/
 
    Admin/Editor records school outgoings — salaries, utilities, supplies, etc.
    Parents cannot access this endpoint.
 
    Supports filtering by category, date range, and free-text search across
    description and reference.
 
    GET  /api/expenditures/summary/  → total spent, breakdown by category
    """
    queryset           = Expenditure.objects.none()
    serializer_class   = ExpenditureSerializer
    permission_classes = [IsAuthenticated]
    pagination_class   = DynamicPageSizePagination
    filter_backends    = [filters.SearchFilter]
    search_fields      = ["description", "reference", "notes"]
 
    def get_queryset(self):
        user = self.request.user
        if is_parent(user):
            return Expenditure.objects.none()  # parents never see expenditures
 
        qs = Expenditure.objects.select_related("recorded_by")
 
        category  = self.request.query_params.get("category")
        date_from = self.request.query_params.get("date_from")
        date_to   = self.request.query_params.get("date_to")
 
        if category:  qs = qs.filter(category=category)
        if date_from: qs = qs.filter(date__gte=date_from)
        if date_to:   qs = qs.filter(date__lte=date_to)
 
        return qs.order_by("-date", "-created_at")
 
    def perform_create(self, serializer):
        if not is_admin_or_editor(self.request.user):
            raise PermissionError("Admin or Editor access required.")
        serializer.save(recorded_by=self.request.user)
 
    def destroy(self, request, *args, **kwargs):
        if not is_admin(request.user):
            return Response({"error": "Only admins can delete expenditure records."}, status=403)
        return super().destroy(request, *args, **kwargs)
 
    @extend_schema(
        summary="Expenditure totals and category breakdown",
        parameters=[
            OpenApiParameter(name="date_from", description="YYYY-MM-DD", required=False, type=OpenApiTypes.DATE),
            OpenApiParameter(name="date_to",   description="YYYY-MM-DD", required=False, type=OpenApiTypes.DATE),
        ],
        responses={200: inline_serializer(
            name="ExpenditureSummaryResponse",
            fields={
                "total_spent":        drf_serializers.FloatField(),
                "count":              drf_serializers.IntegerField(),
                "by_category":        drf_serializers.ListField(child=drf_serializers.DictField()),
            }
        )}
    )
    @action(detail=False, methods=["get"])
    def summary(self, request):
        """
        GET /api/expenditures/summary/?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD
 
        Returns total spent and a per-category breakdown.
        """
        from django.db.models import Sum, Count
 
        qs = self.get_queryset()
        totals = qs.aggregate(total=Sum("amount"), count=Count("id"))
 
        by_category = list(
            qs.values("category")
              .annotate(total=Sum("amount"), count=Count("id"))
              .order_by("-total")
        )
 
        return Response({
            "total_spent": totals["total"] or 0,
            "count":       totals["count"] or 0,
            "by_category": by_category,
        })

# ── ANNOUNCEMENTS ─────────────────────────────────────────────────────────────

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
    """
    /api/announcements/
    Staff posts. All users read. Only admin deletes.
    """
    cache_resource     = "announcements"
    queryset           = Announcement.objects.none()
    serializer_class   = AnnouncementSerializer
    permission_classes = [IsAuthenticated]
    pagination_class   = DynamicPageSizePagination
    filter_backends    = [filters.SearchFilter]
    search_fields      = ["title", "body"]

    def _cache_discriminator(self, request) -> str:
        # Parents only see audience="all"|"parents" announcements;
        # staff see everything.  Two separate cache buckets.
        return "parent" if is_parent(request.user) else "staff"

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
        # VersionedCacheMixin.create() wraps this call and bumps the cache
        # version on success — no extra work needed here.

    def destroy(self, request, *args, **kwargs):
        if not is_admin(request.user):
            return Response({"error": "Only admins can delete announcements."}, status=403)
        return super().destroy(request, *args, **kwargs)  # mixin bumps cache on 204


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
class AssignmentViewSet(VersionedCacheMixin, viewsets.ModelViewSet):
    """
    /api/assignments/
    Staff creates. Parents see their child's class assignments.
    """
    cache_resource     = "assignments"
    queryset           = Assignment.objects.none()
    serializer_class   = AssignmentSerializer
    permission_classes = [IsAuthenticated]
    pagination_class   = DynamicPageSizePagination
    filter_backends    = [filters.SearchFilter]
    search_fields      = ["title", "description"]

    def _cache_discriminator(self, request) -> str:
        # Parents see assignments only for their children's classes — scope by id.
        # Teachers see only their own assignments — scope by id.
        # Admin / editor see everything (query params baked into key).
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
class DevelopmentReportViewSet(VersionedCacheMixin, viewsets.ModelViewSet):
    """
    /api/reports/
    Staff writes. Parent reads published reports for their children only.
    POST /api/reports/<id>/publish/ — admin publishes to parents.
    """
    cache_resource     = "reports"
    queryset           = DevelopmentReport.objects.none()
    serializer_class   = DevelopmentReportSerializer
    permission_classes = [IsAuthenticated]
    pagination_class   = DynamicPageSizePagination
    filter_backends    = [filters.SearchFilter]
    search_fields      = ["comment", "strengths", "areas_to_improve", "student__first_name", "student__last_name"]

    def _cache_discriminator(self, request) -> str:
        # Parents see only published reports for their own children.
        # Teachers see only their classroom's reports.
        # Admin / editor see all reports with optional filters.
        if is_parent(request.user):
            return f"parent:{request.user.id}"
        if is_pure_teacher(request.user):
            return f"teacher:{request.user.id}"
        return "admin_editor"

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
        # publish() bypasses standard CRUD so the mixin cannot detect this write.
        # Bump explicitly — parents must see the newly published report immediately.
        self._bump()
        return Response({"message": f"Report for {report.student.full_name} is now visible to parents."})


# ── AUDIT LOG ─────────────────────────────────────────────────────────────────

@extend_schema(tags=["System Audit"])
@extend_schema_view(
    list=extend_schema(
        summary="List audit log entries (Admin only)",
        parameters=[
            OpenApiParameter(name="user_email",     description="Filter by actor email",                        required=False, type=OpenApiTypes.STR),
            OpenApiParameter(name="user_role",      description="Filter by role: admin|editor|teacher|parent",  required=False, type=OpenApiTypes.STR),
            OpenApiParameter(name="method",         description="HTTP verb: GET|POST|PATCH|DELETE",             required=False, type=OpenApiTypes.STR),
            OpenApiParameter(name="response_status",description="HTTP status code, e.g. 200 or 403",           required=False, type=OpenApiTypes.INT),
            OpenApiParameter(name="resource_type",  description="Resource name, e.g. students|invoices",       required=False, type=OpenApiTypes.STR),
            OpenApiParameter(name="action",         description="Action code, e.g. login.success|delete",      required=False, type=OpenApiTypes.STR),
            OpenApiParameter(name="ip_address",     description="Filter by client IP address",                 required=False, type=OpenApiTypes.STR),
            OpenApiParameter(name="from",           description="ISO date-time: 2025-01-01T00:00:00",          required=False, type=OpenApiTypes.DATETIME),
            OpenApiParameter(name="to",             description="ISO date-time: 2025-12-31T23:59:59",          required=False, type=OpenApiTypes.DATETIME),
            OpenApiParameter(name="failures_only",  description="true — show only 4xx / 5xx responses",        required=False, type=OpenApiTypes.BOOL),
            OpenApiParameter(name="page_size",      description="Results per page (default 25)",               required=False, type=OpenApiTypes.INT),
        ]
    ),
    retrieve=extend_schema(summary="Retrieve a single audit log entry (Admin only)"),
)
class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET /api/audit-logs/         — paginated list with rich filtering
    GET /api/audit-logs/<id>/    — single entry
    GET /api/audit-logs/summary/ — counts grouped by action / resource / status

    Access: Admin only. The table is append-only — no create, update, or delete
    is exposed through the API.
    """
    queryset           = AuditLog.objects.none()
    serializer_class   = AuditLogSerializer
    permission_classes = [IsAuthenticated]
    pagination_class   = DynamicPageSizePagination
    filter_backends    = [filters.SearchFilter]
    search_fields      = ["user_email", "path", "ip_address"]

    def get_queryset(self):
        # ── Access gate ────────────────────────────────────────────────────
        if not is_admin(self.request.user):
            return AuditLog.objects.none()

        qs = AuditLog.objects.select_related("user")
        p  = self.request.query_params

        # ── Filters ────────────────────────────────────────────────────────
        if p.get("user_email"):
            qs = qs.filter(user_email__icontains=p["user_email"])
        if p.get("user_role"):
            qs = qs.filter(user_role=p["user_role"])
        if p.get("method"):
            qs = qs.filter(method=p["method"].upper())
        if p.get("response_status"):
            qs = qs.filter(response_status=p["response_status"])
        if p.get("resource_type"):
            qs = qs.filter(resource_type=p["resource_type"])
        if p.get("action"):
            qs = qs.filter(action=p["action"])
        if p.get("ip_address"):
            qs = qs.filter(ip_address=p["ip_address"])

        # Date range
        if p.get("from"):
            qs = qs.filter(timestamp__gte=p["from"])
        if p.get("to"):
            qs = qs.filter(timestamp__lte=p["to"])

        # Failures shortcut: 4xx and 5xx only
        if p.get("failures_only", "").lower() == "true":
            qs = qs.filter(response_status__gte=400)

        return qs.order_by("-timestamp")

    @extend_schema(
        summary="Aggregated counts for the audit dashboard (Admin only)",
        responses={200: inline_serializer(
            name="AuditSummaryResponse",
            fields={
                "total_requests":   drf_serializers.IntegerField(),
                "failed_requests":  drf_serializers.IntegerField(),
                "error_rate_pct":   drf_serializers.FloatField(),
                "avg_response_ms":  drf_serializers.FloatField(),
                "by_action":        drf_serializers.DictField(child=drf_serializers.IntegerField()),
                "by_resource":      drf_serializers.DictField(child=drf_serializers.IntegerField()),
                "by_status_class":  drf_serializers.DictField(child=drf_serializers.IntegerField()),
                "by_role":          drf_serializers.DictField(child=drf_serializers.IntegerField()),
            }
        )}
    )
    @action(detail=False, methods=["get"])
    def summary(self, request):
        """
        GET /api/audit-logs/summary/
        Returns aggregated counts — useful for an admin dashboard widget.
        Respects the same date-range and filter query params as the list endpoint.
        """
        if not is_admin(request.user):
            return Response({"error": "Admin access required."}, status=403)

        from django.db.models import Count, Avg, IntegerField
        from django.db.models.functions import ExtractHour

        qs = self.get_queryset()

        total    = qs.count()
        failed   = qs.filter(response_status__gte=400).count()
        avg_resp = qs.aggregate(avg=Avg("response_time_ms"))["avg"] or 0

        # Group by action
        by_action = {
            row["action"]: row["cnt"]
            for row in qs.values("action").annotate(cnt=Count("id"))
        }

        # Group by resource_type (top entries)
        by_resource = {
            row["resource_type"]: row["cnt"]
            for row in qs.exclude(resource_type="")
                         .values("resource_type")
                         .annotate(cnt=Count("id"))
                         .order_by("-cnt")[:10]
        }

        # Group by HTTP status class (2xx, 3xx, 4xx, 5xx)
        by_status_class: dict[str, int] = {}
        for row in qs.values("response_status").annotate(cnt=Count("id")):
            cls = f"{row['response_status'] // 100}xx"
            by_status_class[cls] = by_status_class.get(cls, 0) + row["cnt"]

        # Group by actor role
        by_role = {
            row["user_role"] or "anonymous": row["cnt"]
            for row in qs.values("user_role").annotate(cnt=Count("id"))
        }

        return Response({
            "total_requests":  total,
            "failed_requests": failed,
            "error_rate_pct":  round(failed / total * 100, 2) if total else 0,
            "avg_response_ms": round(avg_resp, 1),
            "by_action":       by_action,
            "by_resource":     by_resource,
            "by_status_class": by_status_class,
            "by_role":         by_role,
        })


# ── SYSTEM ────────────────────────────────────────────────────────────────────

@extend_schema(tags=["System"])
class HealthCheckView(APIView):
    """
    GET /api/ — Checks API availability, Database, and Cache.

    Returns 200 if all systems are healthy.
    Returns 503 with a degraded status and per-subsystem detail if any check fails.
    This endpoint is intentionally public (no auth) so uptime monitors can poll it.
    """
    permission_classes = [AllowAny]

    @extend_schema(
        summary="System Health Check",
        responses={
            200: inline_serializer(
                name="HealthCheckSuccess",
                fields={
                    "status":    drf_serializers.CharField(default="healthy"),
                    "checks":    drf_serializers.DictField(child=drf_serializers.CharField()),
                    "timestamp": drf_serializers.DateTimeField(),
                }
            ),
            503: inline_serializer(
                name="HealthCheckFail",
                fields={
                    "status":    drf_serializers.CharField(default="degraded"),
                    "checks":    drf_serializers.DictField(child=drf_serializers.CharField()),
                    "timestamp": drf_serializers.DateTimeField(),
                }
            ),
        }
    )
    def get(self, request):
        checks:  dict[str, str] = {}
        overall: str            = "healthy"

        # ── 1. Database ────────────────────────────────────────────────────
        try:
            connection.ensure_connection()
            with connection.cursor() as cur:
                cur.execute("SELECT 1")
            checks["database"] = "ok"
        except OperationalError as exc:
            checks["database"] = f"error: {exc}"
            overall = "degraded"

        # ── 2. Cache ───────────────────────────────────────────────────────
        try:
            from django.core.cache import cache
            _PROBE_KEY = "_health_check_probe"
            cache.set(_PROBE_KEY, "pong", timeout=5)
            val = cache.get(_PROBE_KEY)
            if val == "pong":
                checks["cache"] = "ok"
            else:
                checks["cache"] = "error: read-back mismatch"
                overall = "degraded"
        except Exception as exc:
            checks["cache"] = f"error: {exc}"
            overall = "degraded"

        http_status = (
            status.HTTP_200_OK
            if overall == "healthy"
            else status.HTTP_503_SERVICE_UNAVAILABLE
        )

        return Response(
            {"status": overall, "checks": checks, "timestamp": timezone.now()},
            status=http_status,
        )

# ── LEAD CAPTURE ────────────────────────────────────────────────────────────────────
@extend_schema(tags=["Lead Capture"])
@extend_schema_view(
    create=extend_schema(
        summary="Submit a public lead/inquiry",
        description="Public endpoint for the website popup. No authentication required.",
        auth=[], # This explicitly removes the auth padlock in Swagger
    ),
    list=extend_schema(summary="List all inquiries (Staff only)"),
    retrieve=extend_schema(summary="Get specific inquiry details (Staff only)"),
    update=extend_schema(summary="Update an inquiry (Staff only)"),
    partial_update=extend_schema(summary="Partially update an inquiry (Staff only)"),
    destroy=extend_schema(summary="Delete an inquiry (Staff only)"),
)
class InquiryViewSet(viewsets.ModelViewSet):
    """
    /api/inquiries/
    POST is open to the public for the website pop-up.
    GET, PATCH, DELETE are restricted to authenticated users.
    """
    queryset = Inquiry.objects.all().order_by('-created_at')
    serializer_class = InquirySerializer
    pagination_class = DynamicPageSizePagination
    filter_backends = [filters.SearchFilter]
    search_fields = ["parent_name", "email", "phone"]

    def get_permissions(self):
        # Open the POST endpoint to the public
        if self.action == 'create':
            return [AllowAny()]
        # Lock everything else down
        return [IsAuthenticated()]