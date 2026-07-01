import uuid
from django.db import models
from django.utils import timezone
from django.contrib.postgres.indexes import GinIndex

from .classroom import ClassRoom

# NOTE: storage imported lazily inside save() — same circular-import
# avoidance as models/users/user.py.  See that file for full explanation.


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
        # validator imported lazily in save()
    )
    current_class  = models.ForeignKey(
        ClassRoom, on_delete=models.SET_NULL, null=True, related_name="students"
    )
    parents        = models.ManyToManyField(
        "school.User", related_name="children", blank=True,
        limit_choices_to={"role": "parent"},
    )
    admission_date = models.DateField(default=timezone.localdate)
    is_active      = models.BooleanField(default=True)
    allergies      = models.TextField(blank=True)
    notes          = models.TextField(blank=True)
    created_at     = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "students"
        ordering = ["current_class__level", "last_name", "first_name"]
        indexes  = [
            GinIndex(
                name="student_search_idx",
                fields=["first_name", "last_name", "admission_number"],
                opclasses=["gin_trgm_ops", "gin_trgm_ops", "gin_trgm_ops"],
            )
        ]

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.admission_number})"

    def save(self, *args, **kwargs):
        if self.profile_photo and hasattr(self.profile_photo, "file"):
            from ...storage import validate_file_size, compress_image  # noqa: F401
            try:
                compressed = compress_image(
                    self.profile_photo, "student",
                    self.profile_photo.name or "student.jpg",
                )
                self.profile_photo.save("student.jpg", compressed, save=False)
            except Exception:
                pass
        super().save(*args, **kwargs)

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"