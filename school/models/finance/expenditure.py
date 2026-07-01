import uuid
from django.db import models
from django.contrib.postgres.indexes import GinIndex


class Expenditure(models.Model):
    """Money spent by the school."""
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

    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    date        = models.DateField(help_text="Date the expenditure occurred")
    category    = models.CharField(max_length=20, choices=CATEGORY)
    description = models.CharField(max_length=300)
    amount      = models.DecimalField(max_digits=12, decimal_places=2)
    reference   = models.CharField(max_length=100, blank=True,
                                   help_text="Receipt number, invoice ref, or bank reference")
    notes       = models.TextField(blank=True)
    recorded_by = models.ForeignKey(
        "school.User", on_delete=models.SET_NULL, null=True,
        related_name="expenditures_recorded",
    )
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "expenditures"
        ordering = ["-date", "-created_at"]
        indexes  = [
            models.Index(fields=["date"],     name="expenditure_date_idx"),
            models.Index(fields=["category"], name="expenditure_cat_idx"),
            GinIndex(
                name="expenditure_search_idx",
                fields=["description", "reference"],
                opclasses=["gin_trgm_ops", "gin_trgm_ops"],
            ),
        ]

    def __str__(self):
        return f"{self.get_category_display()}: ₦{self.amount:,.2f} — {self.date}"
