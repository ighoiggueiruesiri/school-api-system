"""school/serializers.py"""
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth import get_user_model
from drf_spectacular.utils import extend_schema_field
from drf_spectacular.types import OpenApiTypes
from .models import (
    ClassRoom, Term, Student, Attendance,
    Invoice, InvoiceLineItem, Payment, CreditNote, Expenditure,
    Announcement, Assignment, DevelopmentReport, AuditLog, Inquiry, StaffProfile
)

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

class StaffProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = StaffProfile
        fields = "__all__"
        read_only_fields = ["id", "user"]

class UserSerializer(serializers.ModelSerializer):
    staff_profile = StaffProfileSerializer(required=False) # ← Add nested profile

    class Meta:
        model  = User
        fields = ["id","email","first_name","last_name","phone","role","profile_photo","date_joined","is_active", "staff_profile"]
        read_only_fields = ["id","role","date_joined"]

    def update(self, instance, validated_data):
        profile_data = validated_data.pop("staff_profile", None)
        
        # Update main user table
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        # Update or create staff profile if applicable
        if profile_data is not None and instance.role in ["teacher", "non_academic"]:
            StaffProfile.objects.update_or_create(user=instance, defaults=profile_data)

        return instance

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
        # FIX (N+1): ClassRoomViewSet.get_queryset() annotates `student_count_annotated`
        # via a single DB-level COUNT so listing N classrooms costs 1 query, not N+1.
        # We read the annotation here and only fall back to a live query when this
        # serializer is used outside that viewset (e.g. in tests or admin).
        annotated = getattr(obj, "student_count_annotated", None)
        if annotated is not None:
            return annotated
        return obj.students.filter(is_active=True).count()


class TermSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Term
        fields = "__all__"


# ── Students ──────────────────────────────────────────────────────────────────

class StudentSerializer(serializers.ModelSerializer):
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
    student_name     = serializers.SerializerMethodField()
    recorded_by_name = serializers.SerializerMethodField()

    class Meta:
        model  = Attendance
        fields = [
            "id", "date", "status", "reason", "outlook", "created_at",
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
        help_text="List of {student_id, status, reason?} objects."
    )


# ── Finance ───────────────────────────────────────────────────────────────────

class InvoiceLineItemSerializer(serializers.ModelSerializer):
    """
    A single fee row on an invoice.
    `charged_amount` is read-only and equals discounted_amount ?? amount.
    """
    charged_amount = serializers.FloatField(read_only=True)

    class Meta:
        model  = InvoiceLineItem
        fields = [
            "id",
            "description",
            "amount",
            "discounted_amount",
            "charged_amount",
            "sort_order",
        ]
        read_only_fields = ["id", "charged_amount"]


class PaymentSerializer(serializers.ModelSerializer):
    """
    A single instalment or full payment against an invoice.
    `paid_by_name` and `invoice_number` are read-only convenience fields
    for displaying receipt information without extra API calls.

    NOTE: PaymentViewSet.get_queryset() must include:
        select_related("invoice__student__current_class", "invoice__term", "paid_by")
    All SerializerMethodFields below traverse those join paths — without the
    deep select_related the list endpoint would fire N×3 extra queries.
    """
    paid_by_name    = serializers.SerializerMethodField()
    invoice_number  = serializers.SerializerMethodField()
    student_name    = serializers.SerializerMethodField()
    class_name      = serializers.SerializerMethodField()
    term_name       = serializers.SerializerMethodField()

    class Meta:
        model  = Payment
        fields = [
            "id",
            "invoice",
            "invoice_number",
            "student_name",
            "class_name",
            "term_name",
            "amount",
            "method",
            "reference",
            "receipt_number",
            "paid_date",
            "paid_by",
            "paid_by_name",
            "notes",
            "created_at",
        ]
        read_only_fields = ["id", "paid_by", "created_at"]

    @extend_schema_field(OpenApiTypes.STR)
    def get_paid_by_name(self, obj):
        # Covered by select_related("paid_by") in PaymentViewSet
        return obj.paid_by.full_name if obj.paid_by else None

    @extend_schema_field(OpenApiTypes.STR)
    def get_invoice_number(self, obj):
        # Covered by select_related("invoice") in PaymentViewSet
        return obj.invoice.invoice_number

    @extend_schema_field(OpenApiTypes.STR)
    def get_student_name(self, obj):
        # Covered by select_related("invoice__student") in PaymentViewSet
        return obj.invoice.student.full_name

    @extend_schema_field(OpenApiTypes.STR)
    def get_class_name(self, obj):
        # Covered by select_related("invoice__student__current_class") in PaymentViewSet
        cls = obj.invoice.student.current_class
        return cls.name if cls else None

    @extend_schema_field(OpenApiTypes.STR)
    def get_term_name(self, obj):
        # Covered by select_related("invoice__term") in PaymentViewSet
        return str(obj.invoice.term)


class InvoiceSerializer(serializers.ModelSerializer):
    """
    Full invoice representation including nested line items and payments.
    `line_items` are accepted on create/update (writable nested).

    NOTE: InvoiceViewSet.get_queryset() must use:
        select_related("student__current_class", "term")
    `get_class_name` traverses student → current_class; without the deep
    select_related it fires an extra query per invoice row in a list.
    """
    balance      = serializers.FloatField(read_only=True)
    student_name = serializers.SerializerMethodField()
    class_name   = serializers.SerializerMethodField()
    term_name    = serializers.SerializerMethodField()
    payments     = PaymentSerializer(many=True, read_only=True)
    line_items   = InvoiceLineItemSerializer(many=True, required=False)

    class Meta:
        model  = Invoice
        fields = [
            "id",
            "invoice_number",
            "student",
            "student_name",
            "class_name",
            "term",
            "term_name",
            "description",
            "notes",
            "amount",
            "amount_paid",
            "balance",
            "status",
            "due_date",
            "line_items",
            "payments",
            "created_at",
        ]
        read_only_fields = ["id", "invoice_number", "amount_paid", "status", "created_at"]

    @extend_schema_field(OpenApiTypes.STR)
    def get_student_name(self, obj):
        # Covered by select_related("student__current_class") in InvoiceViewSet
        return obj.student.full_name

    @extend_schema_field(OpenApiTypes.STR)
    def get_class_name(self, obj):
        # Covered by select_related("student__current_class") in InvoiceViewSet
        cls = obj.student.current_class
        return cls.name if cls else None

    @extend_schema_field(OpenApiTypes.STR)
    def get_term_name(self, obj):
        return str(obj.term)

    def create(self, validated_data):
        line_items_data = validated_data.pop("line_items", [])
        invoice = Invoice.objects.create(**validated_data)
        for idx, item in enumerate(line_items_data):
            item.setdefault("sort_order", idx)
            InvoiceLineItem.objects.create(invoice=invoice, **item)
        return invoice

    def update(self, instance, validated_data):
        line_items_data = validated_data.pop("line_items", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if line_items_data is not None:
            # Replace all line items on update
            instance.line_items.all().delete()
            for idx, item in enumerate(line_items_data):
                item.setdefault("sort_order", idx)
                InvoiceLineItem.objects.create(invoice=instance, **item)
        return instance


class CreditNoteSerializer(serializers.ModelSerializer):
    student_name   = serializers.CharField(source="student.full_name", read_only=True)
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
            "created_at",
        ]
        read_only_fields = ["id", "logged_by", "created_at"]


class ExpenditureSerializer(serializers.ModelSerializer):
    """
    School outgoing — salary, utilities, supplies, etc.
    `recorded_by_name` is read-only for display.
    `category_display` is the human-readable category label.
    """
    recorded_by_name = serializers.SerializerMethodField()
    category_display = serializers.SerializerMethodField()

    class Meta:
        model = Expenditure
        fields = [
            "id",
            "date",
            "category",
            "category_display",
            "description",
            "amount",
            "reference",
            "notes",
            "recorded_by",
            "recorded_by_name",
            "created_at",
        ]
        read_only_fields = ["id", "recorded_by", "created_at"]

    @extend_schema_field(OpenApiTypes.STR)
    def get_recorded_by_name(self, obj):
        return obj.recorded_by.full_name if obj.recorded_by else None

    @extend_schema_field(OpenApiTypes.STR)
    def get_category_display(self, obj):
        return obj.get_category_display()


# ── Other ─────────────────────────────────────────────────────────────────────

class AnnouncementSerializer(serializers.ModelSerializer):
    author_name = serializers.SerializerMethodField()

    class Meta:
        model  = Announcement
        fields = "__all__"
        read_only_fields = ["author","created_at"]

    @extend_schema_field(OpenApiTypes.STR)
    def get_author_name(self, obj):
        # Covered by select_related("author") in AnnouncementViewSet
        return obj.author.full_name if obj.author else "School"


class AssignmentSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Assignment
        fields = "__all__"
        read_only_fields = ["teacher","created_at"]


class DevelopmentReportSerializer(serializers.ModelSerializer):
    student_name    = serializers.SerializerMethodField()
    written_by_name = serializers.SerializerMethodField()

    class Meta:
        model  = DevelopmentReport
        fields = "__all__"
        read_only_fields = ["written_by","created_at"]

    @extend_schema_field(OpenApiTypes.STR)
    def get_student_name(self, obj):    return obj.student.full_name

    @extend_schema_field(OpenApiTypes.STR)
    def get_written_by_name(self, obj): return obj.written_by.full_name if obj.written_by else None


class InquirySerializer(serializers.ModelSerializer):
    class Meta:
        model = Inquiry
        fields = ['id', 'parent_name', 'email', 'phone', 'interested_class', 'created_at']
        read_only_fields = ['id', 'created_at']


# ── Audit Log ─────────────────────────────────────────────────────────────────

class AuditLogSerializer(serializers.ModelSerializer):
    """
    Read-only serialiser for AuditLog.
    Exposed only to admins via GET /api/audit-logs/.
    """
    action_display = serializers.SerializerMethodField()

    class Meta:
        model  = AuditLog
        fields = [
            "id", "timestamp",
            "user", "user_email", "user_role", "ip_address", "user_agent",
            "method", "path", "query_params", "request_body",
            "response_status", "response_time_ms", "error_detail",
            "resource_type", "resource_id", "action", "action_display",
        ]
        read_only_fields = fields

    @extend_schema_field(OpenApiTypes.STR)
    def get_action_display(self, obj):
        return obj.get_action_display()