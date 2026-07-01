from django.db import models
from django.contrib.postgres.indexes import GinIndex

from .classroom import ClassRoom
from .term      import Term


class Assignment(models.Model):
    """Homework, classwork, or project assigned to a classroom."""
    TYPE = [
        ("homework",  "Homework"),
        ("classwork", "Classwork"),
        ("project",   "Project"),
    ]

    title       = models.CharField(max_length=200)
    description = models.TextField()
    type        = models.CharField(max_length=10, choices=TYPE, default="homework")
    classroom   = models.ForeignKey(ClassRoom, on_delete=models.CASCADE)
    teacher     = models.ForeignKey(
        "school.User", on_delete=models.CASCADE,
        limit_choices_to={"role": "teacher"},
    )
    term        = models.ForeignKey(Term, on_delete=models.CASCADE)
    due_date    = models.DateField()
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "assignments"
        ordering = ["-created_at"]
        indexes  = [
            GinIndex(
                name="assign_search_idx",
                fields=["title", "description"],
                opclasses=["gin_trgm_ops", "gin_trgm_ops"],
            )
        ]

    def __str__(self):
        return f"{self.title} — {self.classroom}"
