from django.db import models


class Term(models.Model):
    """School term, e.g. First Term 2024/2025."""
    TERM_NAMES = [
        ("first",  "First Term"),
        ("second", "Second Term"),
        ("third",  "Third Term"),
    ]
    name          = models.CharField(max_length=10, choices=TERM_NAMES)
    academic_year = models.CharField(max_length=10)    # e.g. "2024/2025"
    start_date    = models.DateField()
    end_date      = models.DateField()
    is_current    = models.BooleanField(default=False)

    class Meta:
        db_table        = "terms"
        unique_together = ["name", "academic_year"]

    def __str__(self):
        return f"{self.get_name_display()} {self.academic_year}"

    def save(self, *args, **kwargs):
        # Enforce only one current term at a time
        if self.is_current:
            Term.objects.exclude(pk=self.pk).update(is_current=False)
        super().save(*args, **kwargs)
