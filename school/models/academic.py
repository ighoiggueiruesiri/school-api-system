import uuid
from django.db import models
from django.utils import timezone
from django.contrib.postgres.indexes import GinIndex
from ..storage import validate_file_size, compress_image


class ClassRoom(models.Model):
    """A class in the school, e.g. Nursery 1, Primary 2."""
    name    = models.CharField(max_length=50, unique=True)
    level   = models.PositiveSmallIntegerField()          # for ordering
    teacher = models.ForeignKey(
        "school.User", on_delete=models.SET_NULL, null=True, blank=True,
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
    parents          = models.ManyToManyField("school.User", related_name="children", blank=True,
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
    recorded_by = models.ForeignKey("school.User", on_delete=models.SET_NULL, null=True)
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


class Assignment(models.Model):
    """Homework or classwork."""
    TYPE = [("homework", "Homework"), ("classwork", "Classwork"), ("project", "Project")]

    title       = models.CharField(max_length=200)
    description = models.TextField()
    type        = models.CharField(max_length=10, choices=TYPE, default="homework")
    classroom   = models.ForeignKey(ClassRoom, on_delete=models.CASCADE)
    teacher     = models.ForeignKey("school.User", on_delete=models.CASCADE, limit_choices_to={"role": "teacher"})
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
    written_by       = models.ForeignKey("school.User", on_delete=models.SET_NULL, null=True)
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