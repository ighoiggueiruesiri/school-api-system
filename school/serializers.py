"""school/serializers.py"""
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth import get_user_model
from drf_spectacular.utils import extend_schema_field
from drf_spectacular.types import OpenApiTypes
from .models import ClassRoom, Term, Student, Attendance, Invoice, Payment, CreditNote, Announcement, Assignment, DevelopmentReport, AuditLog

User = get_user_model()


# ── Auth ──────────────────────────────────────────────────────────────────────

class LoginSerializer(TokenObtainPairSerializer):
    """Adds user info to the login response so the frontend knows the role."""
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["role"]      = user.role
        token["full_name"] = user.full_name
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        data["user"] = {
            "id":        str(self.user.id),
            "email":     self.user.email,
            "full_name": self.user.full_name,
            "role":      self.user.role,
        }
        return data


class RegisterSerializer(serializers.Serializer):
    """Parent self-registration."""
    email      = serializers.EmailField()
    password   = serializers.CharField(write_only=True, min_length=6)
    first_name = serializers.CharField()
    last_name  = serializers.CharField()
    phone      = serializers.CharField(required=False, allow_blank=True)

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Email already registered.")
        return value.lower()

    def create(self, validated_data):
        return User.objects.create_user(
            role="parent", **validated_data
        )


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model  = User
        fields = ["id","email","first_name","last_name","phone","role","profile_photo","date_joined","is_active"]
        read_only_fields = ["id","role","date_joined"]


# ── School structure ──────────────────────────────────────────────────────────

class ClassRoomSerializer(serializers.ModelSerializer):
    teacher_name      = serializers.SerializerMethodField()
    student_count     = serializers.SerializerMethodField()

    class Meta:
        model  = ClassRoom
        fields = "__all__"

    @extend_schema_field(OpenApiTypes.STR)
    def get_teacher_name(self, obj):
        return obj.teacher.full_name if obj.teacher else None

    @extend_schema_field(OpenApiTypes.INT)
    def get_student_count(self, obj):
        return obj.students.filter(is_active=True).count()


class TermSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Term
        fields = "__all__"


# ── Students ──────────────────────────────────────────────────────────────────

class StudentSerializer(serializers.ModelSerializer):
    #full_name         = serializers.ReadOnlyField()
    full_name          = serializers.CharField(read_only=True)
    current_class_name = serializers.SerializerMethodField()
    age               = serializers.SerializerMethodField()

    class Meta:
        model  = Student
        fields = "__all__"
        read_only_fields = ["id","admission_number","created_at"]

    @extend_schema_field(OpenApiTypes.STR)
    def get_current_class_name(self, obj):
        return obj.current_class.name if obj.current_class else None

    @extend_schema_field(OpenApiTypes.INT)
    def get_age(self, obj):
        from django.utils import timezone
        today = timezone.now().date()
        dob   = obj.date_of_birth
        return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


# ── Attendance ────────────────────────────────────────────────────────────────

class AttendanceSerializer(serializers.ModelSerializer):
    
    student_name = serializers.SerializerMethodField()
    recorded_by_name = serializers.SerializerMethodField()

    class Meta:
        model  = Attendance
        #fields = "__all__"
        fields = [
            "id", "date", "status", "reason", "created_at", 
            "student", "student_name", "term", 
            "recorded_by", "recorded_by_name"
        ]
        read_only_fields = ["recorded_by","created_at"]

    @extend_schema_field(OpenApiTypes.STR)
    def get_student_name(self, obj):
        return obj.student.full_name

    @extend_schema_field(OpenApiTypes.STR)
    def get_recorded_by_name(self, obj):
        return obj.recorded_by.full_name if obj.recorded_by else None


class BulkAttendanceSerializer(serializers.Serializer):
    """Mark attendance for a whole class in one API call."""
    date    = serializers.DateField()
    term    = serializers.PrimaryKeyRelatedField(queryset=Term.objects.all())
    records = serializers.ListField(
        child=serializers.DictField(), 
        min_length=1,
        help_text="List of objects containing student_id, status ('present', 'absent', 'late'), and optional reason."
    )


# ── Finance ───────────────────────────────────────────────────────────────────

class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Payment
        fields = "__all__"
        read_only_fields = ["id","created_at"]


class InvoiceSerializer(serializers.ModelSerializer):
    #balance      = serializers.ReadOnlyField()
    balance      = serializers.FloatField(read_only=True)
    student_name = serializers.SerializerMethodField()
    term_name    = serializers.SerializerMethodField()
    payments     = PaymentSerializer(many=True, read_only=True)

    class Meta:
        model  = Invoice
        fields = "__all__"
        read_only_fields = ["id","invoice_number","amount_paid","status","created_at"]

    @extend_schema_field(OpenApiTypes.STR)
    def get_student_name(self, obj): return obj.student.full_name

    @extend_schema_field(OpenApiTypes.STR)
    def get_term_name(self, obj):    return str(obj.term)

class CreditNoteSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="student.full_name", read_only=True)
    logged_by_name = serializers.CharField(source="logged_by.full_name", read_only=True)

    class Meta:
        model = CreditNote
        fields = [
            "id", 
            "student", 
            "student_name", 
            "amount", 
            "reference", 
            "notes", 
            "is_used", 
            "logged_by", 
            "logged_by_name", 
            "created_at"
        ]
        read_only_fields = ["id", "logged_by", "created_at"]
        
# ── Other ─────────────────────────────────────────────────────────────────────

class AnnouncementSerializer(serializers.ModelSerializer):
    author_name = serializers.SerializerMethodField()

    class Meta:
        model  = Announcement
        fields = "__all__"
        read_only_fields = ["author","created_at"]

    @extend_schema_field(OpenApiTypes.STR)
    def get_author_name(self, obj):
        return obj.author.full_name if obj.author else "School"


class AssignmentSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Assignment
        fields = "__all__"
        read_only_fields = ["teacher","created_at"]


class DevelopmentReportSerializer(serializers.ModelSerializer):
    student_name   = serializers.SerializerMethodField()
    written_by_name = serializers.SerializerMethodField()

    class Meta:
        model  = DevelopmentReport
        fields = "__all__"
        read_only_fields = ["written_by","created_at"]

    @extend_schema_field(OpenApiTypes.STR)
    def get_student_name(self, obj):    return obj.student.full_name

    @extend_schema_field(OpenApiTypes.STR)
    def get_written_by_name(self, obj): return obj.written_by.full_name if obj.written_by else None


# ── Audit Log ─────────────────────────────────────────────────────────────────
 
class AuditLogSerializer(serializers.ModelSerializer):
    """
    Read-only serialiser for AuditLog.
 
    Exposed only to admins via GET /api/audit-logs/.
    Supports filtering by user_email, method, response_status,
    resource_type, action, and date range (from / to query params
    handled in the viewset).
    """
    # Human-readable label for the action code
    action_display = serializers.SerializerMethodField()
 
    class Meta:
        model  = AuditLog
        fields = [
            "id",
            "timestamp",
            # actor
            "user",
            "user_email",
            "user_role",
            "ip_address",
            "user_agent",
            # request
            "method",
            "path",
            "query_params",
            "request_body",
            # response
            "response_status",
            "response_time_ms",
            "error_detail",       # ← what actually went wrong (empty on success)
            # classification
            "resource_type",
            "resource_id",
            "action",
            "action_display",
        ]
        # The entire table is immutable from the API — no writes allowed
        read_only_fields = fields
 
    @extend_schema_field(OpenApiTypes.STR)
    def get_action_display(self, obj):
        return obj.get_action_display()