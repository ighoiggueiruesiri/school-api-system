"""
school/models.py

Every model for Giant Step Academy lives here.
Simple. Readable. No hidden files, no signals, no magic.

MODELS:
  User        — one table for all roles (admin, editor, teacher, parent)
  ClassRoom   — a class like "Nursery 1" or "Primary 2"
  Student     — a child enrolled at the school
  Term        — a school term (First, Second, Third)
  Attendance  — one record per student per school day
  Invoice     — a fee bill sent to a parent each term
  Payment     — money received against an invoice
  Announcement — a notice sent to parents / teachers
  DevelopmentReport — teacher's narrative report on a child
  Assignment  — homework or classwork set by a teacher
"""

import uuid
from school.storage import validate_file_size, compress_image
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone
from django.contrib.postgres.indexes import GinIndex

# ─────────────────────────────────────────────
#  USER
# ─────────────────────────────────────────────

class UserRole(models.TextChoices):
    ADMIN   = "admin",   "Admin"
    EDITOR  = "editor",  "Editor"   # ← NEW: view + edit everything, no deletes
    TEACHER = "teacher", "Teacher"
    PARENT  = "parent",  "Parent"


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra):
        if not email:
            raise ValueError("Email is required")
        email = self.normalize_email(email)
        user  = self.model(email=email, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra):
        extra["is_staff"]     = True
        extra["is_superuser"] = True
        extra["role"]         = UserRole.ADMIN
        return self.create_user(email, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    """Single login table for every role."""
    id            = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email         = models.EmailField(unique=True)
    first_name    = models.CharField(max_length=100)
    last_name     = models.CharField(max_length=100)
    phone         = models.CharField(max_length=20, blank=True)
    role          = models.CharField(max_length=10, choices=UserRole.choices, default=UserRole.PARENT)
    profile_photo = models.ImageField(
        upload_to="profiles/", null=True, blank=True,
        validators=[validate_file_size]
    )
    is_active     = models.BooleanField(default=True)
    is_staff      = models.BooleanField(default=False)
    date_joined   = models.DateTimeField(default=timezone.now)

    objects        = UserManager()
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    class Meta:
        db_table = "users"
        indexes = [
            GinIndex(
                name='user_search_idx',
                fields=['first_name', 'last_name', 'email'],
                opclasses=['gin_trgm_ops', 'gin_trgm_ops', 'gin_trgm_ops']
            )
        ]

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.role})"

    def save(self, *args, **kwargs):
        if self.profile_photo and hasattr(self.profile_photo, 'file'):
            try:
                compressed = compress_image(
                    self.profile_photo, "profile",
                    self.profile_photo.name or "profile.jpg"
                )
                self.profile_photo.save("profile.jpg", compressed, save=False)
            except Exception:
                pass  # compression failed — save original
        super().save(*args, **kwargs)

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"


# ─────────────────────────────────────────────
#  ACADEMIC STRUCTURE
# ─────────────────────────────────────────────

class ClassRoom(models.Model):
    """A class in the school, e.g. Nursery 1, Primary 2."""
    name    = models.CharField(max_length=50, unique=True)
    level   = models.PositiveSmallIntegerField()          # for ordering
    teacher = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="class_taught",
        limit_choices_to={"role": "teacher"},
    )
    capacity = models.PositiveSmallIntegerField(default=20)

    class Meta:
        db_table  = "classrooms"
        ordering  = ["level"]
        indexes = [
            GinIndex(
                name='classroom_search_idx',
                fields=['name'],
                opclasses=['gin_trgm_ops']
            )
        ]

    def __str__(self):
        return self.name


class Term(models.Model):
    """School term, e.g. First Term 2024/2025."""
    TERM_NAMES = [("first", "First Term"), ("second", "Second Term"), ("third", "Third Term")]
    name          = models.CharField(max_length=10, choices=TERM_NAMES)
    academic_year = models.CharField(max_length=10)    # "2024/2025"
    start_date    = models.DateField()
    end_date      = models.DateField()
    is_current    = models.BooleanField(default=False)

    class Meta:
        db_table        = "terms"
        unique_together = ["name", "academic_year"]

    def __str__(self):
        return f"{self.get_name_display()} {self.academic_year}"

    def save(self, *args, **kwargs):
        if self.is_current:
            Term.objects.exclude(pk=self.pk).update(is_current=False)
        super().save(*args, **kwargs)


# ─────────────────────────────────────────────
#  STUDENT
# ─────────────────────────────────────────────

class Student(models.Model):
    """A child enrolled at the school."""
    GENDER = [("male", "Male"), ("female", "Female")]

    id               = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    admission_number = models.CharField(max_length=20, unique=True)
    first_name       = models.CharField(max_length=100)
    last_name        = models.CharField(max_length=100)
    date_of_birth    = models.DateField()
    gender           = models.CharField(max_length=10, choices=GENDER)
    profile_photo    = models.ImageField(
        upload_to="students/", null=True, blank=True,
        validators=[validate_file_size]
    )
    current_class    = models.ForeignKey(ClassRoom, on_delete=models.SET_NULL, null=True, related_name="students")
    parents          = models.ManyToManyField(User, related_name="children", blank=True,
                                              limit_choices_to={"role": "parent"})
    admission_date   = models.DateField(default=timezone.now)
    is_active        = models.BooleanField(default=True)
    allergies        = models.TextField(blank=True)
    notes            = models.TextField(blank=True)
    created_at       = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "students"
        ordering = ["current_class__level", "last_name", "first_name"]
        indexes = [
            GinIndex(
                name='student_search_idx',
                fields=['first_name', 'last_name', 'admission_number'],
                opclasses=['gin_trgm_ops', 'gin_trgm_ops', 'gin_trgm_ops']
            )
        ]

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.admission_number})"

    def save(self, *args, **kwargs):
        if self.profile_photo and hasattr(self.profile_photo, 'file'):
            try:
                compressed = compress_image(
                    self.profile_photo, "student",
                    self.profile_photo.name or "student.jpg"
                )
                self.profile_photo.save("student.jpg", compressed, save=False)
            except Exception:
                pass
        super().save(*args, **kwargs)

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"


# ─────────────────────────────────────────────
#  ATTENDANCE
# ─────────────────────────────────────────────

class Attendance(models.Model):
    STATUS = [
        ("present", "Present"),
        ("absent",  "Absent"),
        ("late",    "Late"),
        ("excused", "Excused"),
    ]
    student     = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="attendance")
    date        = models.DateField()
    status      = models.CharField(max_length=10, choices=STATUS)
    reason      = models.CharField(max_length=200, blank=True)
    recorded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    term        = models.ForeignKey(Term, on_delete=models.CASCADE)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table        = "attendance"
        unique_together = ["student", "date"]   # one record per student per day
        ordering        = ["-date"]
        indexes = [
            GinIndex(
                name='attendance_search_idx',
                fields=['reason'],
                opclasses=['gin_trgm_ops']
            )
        ]

    def __str__(self):
        return f"{self.student.full_name} — {self.date} — {self.status}"


# ─────────────────────────────────────────────
#  FINANCE
# ─────────────────────────────────────────────

class Invoice(models.Model):
    """A fee bill issued to a parent for their child's term."""
    STATUS = [
        ("unpaid",   "Unpaid"),
        ("partial",  "Partially Paid"),
        ("paid",     "Paid"),
    ]
    id             = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invoice_number = models.CharField(max_length=30, unique=True)
    student        = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="invoices")
    term           = models.ForeignKey(Term, on_delete=models.CASCADE)
    description    = models.CharField(max_length=200)
    amount         = models.DecimalField(max_digits=12, decimal_places=2)
    amount_paid    = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status         = models.CharField(max_length=10, choices=STATUS, default="unpaid")
    due_date       = models.DateField()
    created_at     = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "invoices"
        ordering = ["-created_at"]
        indexes = [
            GinIndex(
                name='invoice_search_idx',
                fields=['invoice_number', 'description'],
                opclasses=['gin_trgm_ops', 'gin_trgm_ops']
            )
        ]

    def __str__(self):
        return f"{self.invoice_number} — {self.student.full_name}"

    @property
    def balance(self):
        return self.amount - self.amount_paid

    def update_status(self):
        if self.amount_paid >= self.amount:
            self.status = "paid"
        elif self.amount_paid > 0:
            self.status = "partial"
        else:
            self.status = "unpaid"
        self.save(update_fields=["status"])


class Payment(models.Model):
    """Money received against an invoice."""
    METHOD = [
        ("cash",          "Cash"),
        ("bank_transfer", "Bank Transfer"),
        ("pos",           "POS"),
        ("paystack",      "Paystack"),
    ]
    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invoice    = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="payments")
    amount     = models.DecimalField(max_digits=12, decimal_places=2)
    method     = models.CharField(max_length=20, choices=METHOD)
    reference  = models.CharField(max_length=100, blank=True)
    paid_by    = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    notes      = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "payments"
        ordering = ["-created_at"]
        indexes = [
            GinIndex(
                name='payment_search_idx',
                fields=['reference', 'notes'],
                opclasses=['gin_trgm_ops', 'gin_trgm_ops']
            )
        ]

    def __str__(self):
        return f"₦{self.amount:,.2f} — {self.invoice.student.full_name}"

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.amount != self.invoice.balance:
            raise ValidationError({
                "amount": (
                    f"Payment amount (₦{self.amount}) must exactly match the invoice balance "
                    f"(₦{self.invoice.balance}). Partial or over-payments are not allowed."
                )
            })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
        self.invoice.amount_paid = self.amount
        self.invoice.status = "paid"
        self.invoice.save(update_fields=["amount_paid", "status"])


class CreditNote(models.Model):
    """Manually logged student overpayments or credit balances."""
    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student    = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="credit_notes")
    amount     = models.DecimalField(max_digits=12, decimal_places=2)
    reference  = models.CharField(max_length=100)
    notes      = models.TextField(blank=True)
    is_used    = models.BooleanField(default=False)
    logged_by  = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "credit_notes"
        ordering = ["-created_at"]
        indexes = [
            GinIndex(
                name='credit_search_idx',
                fields=['reference', 'notes'],
                opclasses=['gin_trgm_ops', 'gin_trgm_ops']
            )
        ]

    def __str__(self):
        return f"Credit Note: ₦{self.amount:,.2f} — {self.student.full_name}"


# ─────────────────────────────────────────────
#  COMMUNICATIONS
# ─────────────────────────────────────────────

class Announcement(models.Model):
    """School notice sent to parents or teachers."""
    AUDIENCE = [
        ("all",      "Everyone"),
        ("parents",  "All Parents"),
        ("teachers", "All Teachers"),
    ]
    title      = models.CharField(max_length=200)
    body       = models.TextField()
    audience   = models.CharField(max_length=10, choices=AUDIENCE, default="all")
    author     = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "announcements"
        ordering = ["-created_at"]
        indexes = [
            GinIndex(
                name='announce_search_idx',
                fields=['title', 'body'],
                opclasses=['gin_trgm_ops', 'gin_trgm_ops']
            )
        ]

    def __str__(self):
        return self.title


# ─────────────────────────────────────────────
#  ACADEMIC CONTENT
# ─────────────────────────────────────────────

class Assignment(models.Model):
    """Homework or classwork."""
    TYPE = [("homework", "Homework"), ("classwork", "Classwork"), ("project", "Project")]

    title       = models.CharField(max_length=200)
    description = models.TextField()
    type        = models.CharField(max_length=10, choices=TYPE, default="homework")
    classroom   = models.ForeignKey(ClassRoom, on_delete=models.CASCADE)
    teacher     = models.ForeignKey(User, on_delete=models.CASCADE, limit_choices_to={"role": "teacher"})
    term        = models.ForeignKey(Term, on_delete=models.CASCADE)
    due_date    = models.DateField()
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "assignments"
        ordering = ["-created_at"]
        indexes = [
            GinIndex(
                name='assign_search_idx',
                fields=['title', 'description'],
                opclasses=['gin_trgm_ops', 'gin_trgm_ops']
            )
        ]

    def __str__(self):
        return f"{self.title} — {self.classroom}"


class DevelopmentReport(models.Model):
    """Teacher's narrative report on a child each term."""
    student          = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="reports")
    term             = models.ForeignKey(Term, on_delete=models.CASCADE)
    written_by       = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    comment          = models.TextField()
    strengths        = models.TextField(blank=True)
    areas_to_improve = models.TextField(blank=True)
    confidence       = models.PositiveSmallIntegerField(default=3)
    teamwork         = models.PositiveSmallIntegerField(default=3)
    is_published     = models.BooleanField(default=False)
    created_at       = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table        = "development_reports"
        unique_together = ["student", "term"]
        ordering        = ["-created_at"]
        indexes = [
            GinIndex(
                name='report_search_idx',
                fields=['comment', 'strengths', 'areas_to_improve'],
                opclasses=['gin_trgm_ops', 'gin_trgm_ops', 'gin_trgm_ops']
            )
        ]

    def __str__(self):
        return f"Report: {self.student.full_name} — {self.term}"


# ─────────────────────────────────────────────
#  AUDIT LOG
# ─────────────────────────────────────────────
 
class AuditLog(models.Model):
    """
    Immutable record of every API action — who did what, when, and with what result.
 
    Written by AuditLogMiddleware after every response. Never updated or deleted
    through the application; treated as append-only. Admins can query via
    GET /api/audit-logs/.
 
    Fields
    ------
    user          → the authenticated user (NULL for anonymous / unauthenticated)
    user_email    → denormalised so logs survive user deletion
    user_role     → denormalised role at the time of the request
    ip_address    → real client IP (respects X-Forwarded-For from a trusted proxy)
    user_agent    → browser / app string, truncated to 500 chars
    method        → HTTP verb (GET POST PATCH DELETE …)
    path          → request path, e.g. /api/students/
    query_params  → ?key=value dict (JSON)
    request_body  → sanitised payload — passwords/tokens replaced with "***"
    response_status → HTTP status code returned
    response_time_ms → round-trip time in milliseconds
    resource_type → first URL segment after /api/, e.g. "students", "invoices"
    resource_id   → second URL segment when present, e.g. the UUID of a student
    action        → derived verb: login.success | login.failed | logout | register
                    | create | read | update | delete | bulk | action | health_check
    timestamp     → auto_now_add — immutable once written
    """
 
    ACTION_CHOICES = [
        ("login.success", "Login Success"),
        ("login.failed",  "Login Failed"),
        ("logout",        "Logout"),
        ("register",      "Register"),
        ("create",        "Create"),
        ("read",          "Read"),
        ("update",        "Update"),
        ("delete",        "Delete"),
        ("bulk",          "Bulk Operation"),
        ("action",        "Custom Action"),
        ("health_check",  "Health Check"),
        ("error",         "Server Error"),
    ]
 
    id               = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # ── Actor ─────────────────────────────────────────────────────────────────
    user             = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="audit_logs",
        help_text="NULL for anonymous / unauthenticated requests.",
    )
    user_email       = models.EmailField(blank=True, help_text="Denormalised — survives user deletion.")
    user_role        = models.CharField(max_length=10, blank=True, help_text="Role at request time.")
    ip_address       = models.GenericIPAddressField(null=True, blank=True)
    user_agent       = models.TextField(blank=True)
    # ── Request ───────────────────────────────────────────────────────────────
    method           = models.CharField(max_length=10)
    path             = models.CharField(max_length=500)
    query_params     = models.JSONField(default=dict, blank=True)
    request_body     = models.JSONField(default=dict, blank=True, help_text="Sanitised — no passwords/tokens.")
    # ── Response ──────────────────────────────────────────────────────────────
    response_status  = models.PositiveSmallIntegerField()
    response_time_ms = models.PositiveIntegerField(default=0)
    # ── Classification ────────────────────────────────────────────────────────
    resource_type    = models.CharField(max_length=50, blank=True, help_text="e.g. students, invoices")
    resource_id      = models.CharField(max_length=100, blank=True)
    action           = models.CharField(max_length=20, choices=ACTION_CHOICES, default="read")
    # ── Meta ──────────────────────────────────────────────────────────────────
    error_detail     = models.TextField(
        blank=True,
        help_text=(
            "Human-readable description of what went wrong, populated for every "
            "4xx / 5xx response. Empty for successful requests. "
            "Examples: 'email: This field is required.' | "
            "'Only admins can delete students.' | "
            "'Given token not valid for any token type'"
        ),
    )
    timestamp        = models.DateTimeField(auto_now_add=True, db_index=True)
 
    class Meta:
        db_table = "audit_logs"
        ordering = ["-timestamp"]
        indexes  = [
            # fast look-ups the admin dashboard will need most
            models.Index(fields=["user",            "-timestamp"], name="audit_user_ts_idx"),
            models.Index(fields=["resource_type",   "-timestamp"], name="audit_resource_ts_idx"),
            models.Index(fields=["response_status", "-timestamp"], name="audit_status_ts_idx"),
            models.Index(fields=["action",          "-timestamp"], name="audit_action_ts_idx"),
            models.Index(fields=["ip_address",      "-timestamp"], name="audit_ip_ts_idx"),
        ]
 
    def __str__(self):
        actor = self.user_email or "anon"
        return f"[{self.timestamp:%Y-%m-%d %H:%M:%S}] {actor} {self.method} {self.path} → {self.response_status}"

# ─────────────────────────────────────────────
#  INQUIRY
# ─────────────────────────────────────────────
class Inquiry(models.Model):
    """Lead capture from the frontend pop-up."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    parent_name = models.CharField(max_length=150)
    email = models.EmailField()
    phone = models.CharField(max_length=20)
    interested_class = models.CharField(max_length=50, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "inquiries"
        ordering = ["-created_at"]
        indexes = [
            GinIndex(
                name='inquiry_search_idx',
                fields=['parent_name', 'email', 'phone'],
                opclasses=['gin_trgm_ops', 'gin_trgm_ops', 'gin_trgm_ops']
            )
        ]

    def __str__(self):
        return f"{self.parent_name} - {self.phone}"