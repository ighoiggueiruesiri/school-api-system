from django.db import models
from django.contrib.postgres.indexes import GinIndex

from .student import Student
from .term    import Term


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
    outlook     = models.CharField(max_length=255, blank=True,
                                   help_text="Child's mood/outlook on arrival")
    recorded_by = models.ForeignKey("school.User", on_delete=models.SET_NULL, null=True)
    term        = models.ForeignKey(Term, on_delete=models.CASCADE)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table        = "attendance"
        unique_together = ["student", "date"]   # one record per student per day
        ordering        = ["-date"]
        indexes         = [
            GinIndex(
                name="attendance_search_idx",
                fields=["reason", "outlook"],
                opclasses=["gin_trgm_ops", "gin_trgm_ops"],
            )
        ]

    def __str__(self):
        return f"{self.student.full_name} — {self.date} — {self.status}"
