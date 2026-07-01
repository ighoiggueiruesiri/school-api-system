import uuid
from django.db import models
from django.contrib.postgres.indexes import GinIndex


class CreditNote(models.Model):
    """Manually logged student overpayments or credit balances."""
    id        = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student   = models.ForeignKey(
        "school.Student", on_delete=models.CASCADE, related_name="credit_notes"
    )
    amount    = models.DecimalField(max_digits=12, decimal_places=2)
    reference = models.CharField(max_length=100)
    notes     = models.TextField(blank=True)
    is_used   = models.BooleanField(default=False)
    logged_by = models.ForeignKey("school.User", on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "credit_notes"
        ordering = ["-created_at"]
        indexes  = [
            GinIndex(
                name="credit_search_idx",
                fields=["reference", "notes"],
                opclasses=["gin_trgm_ops", "gin_trgm_ops"],
            )
        ]

    def __str__(self):
        return f"Credit Note: ₦{self.amount:,.2f} — {self.student.full_name}"
