from django.db import models
from django.contrib.postgres.indexes import GinIndex


class ClassRoom(models.Model):
    """A class in the school, e.g. Nursery 1, Primary 2."""
    name     = models.CharField(max_length=50, unique=True)
    level    = models.PositiveSmallIntegerField()          # used for ordering
    teacher  = models.ForeignKey(
        "school.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="class_taught",
        limit_choices_to={"role": "teacher"},
    )
    capacity = models.PositiveSmallIntegerField(default=20)

    class Meta:
        db_table = "classrooms"
        ordering = ["level"]
        indexes  = [
            GinIndex(
                name="classroom_search_idx",
                fields=["name"],
                opclasses=["gin_trgm_ops"],
            )
        ]

    def __str__(self):
        return self.name
