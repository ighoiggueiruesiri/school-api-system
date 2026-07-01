import uuid
from django.db import models
from django.utils import timezone
from django.contrib.postgres.indexes import GinIndex
from django.core.exceptions import ValidationError
from django.db.models import Sum

from .invoice import Invoice


class Payment(models.Model):
    """Money received against an invoice — supports instalment payments."""
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
    paid_by        = models.ForeignKey("school.User", on_delete=models.SET_NULL, null=True)
    notes          = models.TextField(blank=True)
    created_at     = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "payments"
        ordering = ["-paid_date", "-created_at"]
        indexes  = [
            GinIndex(
                name="payment_search_idx",
                fields=["reference", "notes"],
                opclasses=["gin_trgm_ops", "gin_trgm_ops"],
            )
        ]

    def __str__(self):
        return f"₦{self.amount:,.2f} — {self.invoice.student.full_name} ({self.paid_date})"

    def clean(self):
        """
        Validates instalment payments:
        - Amount must be positive.
        - New payment must not push total paid above invoice amount.
        """
        if self.amount <= 0:
            raise ValidationError({"amount": "Payment amount must be greater than zero."})

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
        # Keep invoice.amount_paid in sync and re-evaluate status
        total_paid = (
            Payment.objects
            .filter(invoice=self.invoice)
            .aggregate(total=Sum("amount"))["total"]
        ) or 0
        Invoice.objects.filter(pk=self.invoice.pk).update(amount_paid=total_paid)
        self.invoice.amount_paid = total_paid
        self.invoice.update_status()
