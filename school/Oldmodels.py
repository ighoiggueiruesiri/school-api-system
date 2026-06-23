"""
school/models.py

Every model for Giant Step Academy lives here.
Simple. Readable. No hidden files, no signals, no magic.

MODELS:
  User              — one table for all roles (admin, editor, teacher, parent)
  ClassRoom         — a class like "Nursery 1" or "Primary 2"
  Student           — a child enrolled at the school
  Term              — a school term (First, Second, Third)
  Attendance        — one record per student per school day
  Invoice           — a fee bill sent to a parent each term
  InvoiceLineItem   — individual fee rows on an invoice (Tuition, Diction, etc.)
  Payment           — money received against an invoice (supports installments)
  CreditNote        — manually logged student overpayments or credit balances
  Expenditure       — money spent by the school (salaries, supplies, etc.)
  Announcement      — a notice sent to parents / teachers
  DevelopmentReport — teacher's narrative report on a child
  Assignment        — homework or classwork set by a teacher
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
    EDITOR  = "editor",  "Editor"  
    TEACHER = "teacher", "Teacher"
    NON_ACADEMIC = "non_academic", "Non-Academic Staff"
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
    role          = models.CharField(max_length=20, choices=UserRole.choices, default=UserRole.PARENT)
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

class StaffProfile(models.Model):
    """
    Extended HR bio-data specifically for Teachers and Non-Academic Staff.
    Maps directly to the official Employee Bio-Data form.
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="staff_profile")
    
    # Demographics
    date_of_birth   = models.DateField(null=True, blank=True)
    gender          = models.CharField(max_length=10, choices=[("male", "Male"), ("female", "Female")], blank=True)
    marital_status  = models.CharField(max_length=20, blank=True)
    nationality     = models.CharField(max_length=50, default="Nigerian")
    state_of_origin = models.CharField(max_length=50, blank=True)
    lga             = models.CharField(max_length=50, blank=True)
    home_address    = models.TextField(blank=True)

    # Emergency & Family
    spouse_name                = models.CharField(max_length=100, blank=True)
    spouse_phone               = models.CharField(max_length=20, blank=True)
    emergency_contact_name     = models.CharField(max_length=100, blank=True)
    emergency_contact_phone    = models.CharField(max_length=20, blank=True)
    emergency_contact_relation = models.CharField(max_length=50, blank=True)

    # Education & Experience
    highest_qualification = models.CharField(max_length=100, blank=True)
    institution           = models.CharField(max_length=150, blank=True)
    year_attained         = models.CharField(max_length=4, blank=True)
    previous_employer     = models.CharField(max_length=150, blank=True)
    previous_job_title    = models.CharField(max_length=100, blank=True)
    teaching_philosophy   = models.TextField(blank=True, help_text="Teaching approach and philosophy")

    # Medical
    blood_group        = models.CharField(max_length=5, blank=True)
    genotype           = models.CharField(max_length=5, blank=True)
    medical_conditions = models.TextField(blank=True)

    # Shortees (Guarantors)
    shortee_1_name  = models.CharField(max_length=100, blank=True)
    shortee_1_phone = models.CharField(max_length=20, blank=True)
    shortee_2_name  = models.CharField(max_length=100, blank=True)
    shortee_2_phone = models.CharField(max_length=20, blank=True)

    class Meta:
        db_table = "staff_profiles"

    def __str__(self):
        return f"Staff Profile: {self.user.full_name}"

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
    outlook     = models.CharField(max_length=255, blank=True, help_text="Child's mood/outlook on arrival")
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
                fields=['reason', 'outlook'],
                opclasses=['gin_trgm_ops', 'gin_trgm_ops']
            )
        ]

    def __str__(self):
        return f"{self.student.full_name} — {self.date} — {self.status}"


# ─────────────────────────────────────────────
#  FINANCE
# ─────────────────────────────────────────────

class Invoice(models.Model):
    """
    A fee bill issued to a parent for their child's term.

    `amount`     — the total amount owed (set by admin; can be auto-filled from line items)
    `amount_paid`— running total updated whenever a Payment is saved
    `status`     — auto-managed: unpaid / partial / paid
    `description`— short title/label (e.g. "Third Term 2025/2026 Fees")
    `notes`      — freetext for admin (e.g. sibling discount applied)
    Line items are stored in InvoiceLineItem for itemized breakdowns.
    """
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
    notes          = models.TextField(blank=True)
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
        """Recalculate and persist status. Called by Payment.save()."""
        if self.amount_paid >= self.amount:
            new_status = "paid"
        elif self.amount_paid > 0:
            new_status = "partial"
        else:
            new_status = "unpaid"
        Invoice.objects.filter(pk=self.pk).update(status=new_status)
        self.status = new_status


class InvoiceLineItem(models.Model):
    """
    An individual fee row on an invoice.
    Mirrors the breakdown seen on the school's physical invoices:
    Tuition, Diction, After School, Gymnastics, etc.

    `amount`            — original/full price
    `discounted_amount` — actual amount charged (None = no discount, use `amount`)
    """
    invoice           = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="line_items")
    description       = models.CharField(max_length=200)
    amount            = models.DecimalField(max_digits=12, decimal_places=2)
    discounted_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    sort_order        = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = "invoice_line_items"
        ordering = ["sort_order", "id"]

    def __str__(self):
        charged = self.discounted_amount if self.discounted_amount is not None else self.amount
        return f"{self.description}: ₦{charged:,.2f} (Invoice {self.invoice.invoice_number})"

    @property
    def charged_amount(self):
        """The actual billable amount for this line."""
        return self.discounted_amount if self.discounted_amount is not None else self.amount


class Payment(models.Model):
    """
    Money received against an invoice — supports instalment payments.

    Multiple Payment records can exist for one Invoice.
    Each save() recalculates invoice.amount_paid as the sum of all payments.

    `receipt_number` — internal serial number printed on the receipt PDF
    `paid_date`      — the date the money was physically received
    """
    METHOD = [
        ("cash",          "Cash"),
        ("bank_transfer", "Bank Transfer"),
        ("pos",           "POS"),
        ("paystack",      "Paystack"),
    ]
    id             = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invoice        = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="payments")
    amount         = models.DecimalField(max_digits=12, decimal_places=2)
    method         = models.CharField(max_length=20, choices=METHOD)
    reference      = models.CharField(max_length=100, blank=True)
    receipt_number = models.CharField(max_length=50, blank=True,
                                      help_text="Internal receipt serial, e.g. RCP-2025-001")
    paid_date      = models.DateField(default=timezone.now,
                                      help_text="Date money was physically received")
    paid_by        = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    notes          = models.TextField(blank=True)
    created_at     = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "payments"
        ordering = ["-paid_date", "-created_at"]
        indexes = [
            GinIndex(
                name='payment_search_idx',
                fields=['reference', 'notes'],
                opclasses=['gin_trgm_ops', 'gin_trgm_ops']
            )
        ]

    def __str__(self):
        return f"₦{self.amount:,.2f} — {self.invoice.student.full_name} ({self.paid_date})"

    def clean(self):
        """
        Allow instalment payments. Rules:
        - Amount must be positive.
        - New payment must not push total paid above the invoice amount.
        """
        from django.core.exceptions import ValidationError
        from django.db.models import Sum

        if self.amount <= 0:
            raise ValidationError({"amount": "Payment amount must be greater than zero."})

        # Sum of existing payments (excluding self if this is an edit)
        already_paid = (
            Payment.objects
            .filter(invoice=self.invoice)
            .exclude(pk=self.pk)
            .aggregate(total=Sum("amount"))["total"]
        ) or 0

        remaining = self.invoice.amount - already_paid
        if self.amount > remaining:
            raise ValidationError({
                "amount": (
                    f"Payment of ₦{self.amount:,.2f} would exceed the remaining "
                    f"balance of ₦{remaining:,.2f} on this invoice."
                )
            })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
        # Recalculate invoice.amount_paid as the sum of ALL payments for this invoice
        from django.db.models import Sum
        total_paid = (
            Payment.objects
            .filter(invoice=self.invoice)
            .aggregate(total=Sum("amount"))["total"]
        ) or 0
        Invoice.objects.filter(pk=self.invoice.pk).update(amount_paid=total_paid)
        self.invoice.amount_paid = total_paid
        self.invoice.update_status()


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


class Expenditure(models.Model):
    """
    Money spent by the school.

    Captures operational costs — salaries, utilities, supplies, etc.
    Stored separately from Invoice/Payment so income and outgoings can be
    reported independently.
    """
    CATEGORY = [
        ("salary",      "Staff Salary"),
        ("utilities",   "Utilities"),
        ("supplies",    "School Supplies"),
        ("maintenance", "Maintenance & Repairs"),
        ("transport",   "Transport"),
        ("events",      "Events & Activities"),
        ("marketing",   "Marketing & Outreach"),
        ("other",       "Other"),
    ]

    id           = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    date         = models.DateField(help_text="Date the expenditure occurred")
    category     = models.CharField(max_length=20, choices=CATEGORY)
    description  = models.CharField(max_length=300)
    amount       = models.DecimalField(max_digits=12, decimal_places=2)
    reference    = models.CharField(max_length=100, blank=True,
                                    help_text="Receipt number, invoice ref, or bank reference")
    notes        = models.TextField(blank=True)
    recorded_by  = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True,
        related_name="expenditures_recorded",
    )
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "expenditures"
        ordering = ["-date", "-created_at"]
        indexes = [
            models.Index(fields=["date"],     name="expenditure_date_idx"),
            models.Index(fields=["category"], name="expenditure_cat_idx"),
            GinIndex(
                name='expenditure_search_idx',
                fields=['description', 'reference'],
                opclasses=['gin_trgm_ops', 'gin_trgm_ops']
            )
        ]

    def __str__(self):
        return f"{self.get_category_display()}: ₦{self.amount:,.2f} — {self.date}"


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
    user             = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="audit_logs",
    )
    user_email       = models.EmailField(blank=True)
    user_role        = models.CharField(max_length=10, blank=True)
    ip_address       = models.GenericIPAddressField(null=True, blank=True)
    user_agent       = models.TextField(blank=True)
    method           = models.CharField(max_length=10)
    path             = models.CharField(max_length=500)
    query_params     = models.JSONField(default=dict, blank=True)
    request_body     = models.JSONField(default=dict, blank=True)
    response_status  = models.PositiveSmallIntegerField()
    response_time_ms = models.PositiveIntegerField(default=0)
    resource_type    = models.CharField(max_length=50, blank=True)
    resource_id      = models.CharField(max_length=100, blank=True)
    action           = models.CharField(max_length=20, choices=ACTION_CHOICES, default="read")
    error_detail     = models.TextField(blank=True)
    timestamp        = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "audit_logs"
        ordering = ["-timestamp"]
        indexes  = [
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