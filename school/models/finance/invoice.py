import uuid
from django.db import models
from django.contrib.postgres.indexes import GinIndex


class Invoice(models.Model):
    """
    A fee bill issued to a parent for their child's term.

    `amount`      — total amount owed (set by admin; can be auto-filled from line items)
    `amount_paid` — running total updated whenever a Payment is saved
    `status`      — auto-managed: unpaid / partial / paid
    `description` — short title/label (e.g. "Third Term 2025/2026 Fees")
    `notes`       — freetext for admin (e.g. sibling discount applied)

    Line items are stored in InvoiceLineItem for itemised breakdowns.
    """
    STATUS = [
        ("unpaid",  "Unpaid"),
        ("partial", "Partially Paid"),
        ("paid",    "Paid"),
    ]

    id             = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invoice_number = models.CharField(max_length=30, unique=True)
    student        = models.ForeignKey(
        "school.Student", on_delete=models.CASCADE, related_name="invoices"
    )
    term           = models.ForeignKey("school.Term", on_delete=models.CASCADE)
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
        indexes  = [
            GinIndex(
                name="invoice_search_idx",
                fields=["invoice_number", "description"],
                opclasses=["gin_trgm_ops", "gin_trgm_ops"],
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
    Mirrors the breakdown seen on physical invoices:
    Tuition, Diction, After School, Gymnastics, etc.
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
