import uuid
from django.db import models
from django.utils import timezone
from django.contrib.postgres.indexes import GinIndex
from django.core.exceptions import ValidationError
from django.db.models import Sum


class Invoice(models.Model):
    """
    A fee bill issued to a parent for their child's term.

    `amount`     — the total amount owed (set by admin; can be auto-filled from line items)
    `amount_paid`— running total updated whenever a Payment is saved
    `status`     — auto-managed: unpaid / partial / paid
    `description`— short title/label (e.g. "Third Term 2025/2026 Fees")
    `notes`      — freetext for admin (e.g. sibling discount applied)
    Line items are stored in InvoiceLineItem for itemized breakdowns.
    """
    STATUS = [
        ("unpaid",   "Unpaid"),
        ("partial",  "Partially Paid"),
        ("paid",     "Paid"),
    ]
    id             = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invoice_number = models.CharField(max_length=30, unique=True)
    student        = models.ForeignKey("school.Student", on_delete=models.CASCADE, related_name="invoices")
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
        indexes = [
            GinIndex(
                name='invoice_search_idx',
                fields=['invoice_number', 'description'],
                opclasses=['gin_trgm_ops', 'gin_trgm_ops']
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
    Mirrors the breakdown seen on the school's physical invoices:
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


class Payment(models.Model):
    """
    Money received against an invoice — supports instalment payments.
    """
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
        indexes = [
            GinIndex(
                name='payment_search_idx',
                fields=['reference', 'notes'],
                opclasses=['gin_trgm_ops', 'gin_trgm_ops']
            )
        ]

    def __str__(self):
        return f"₦{self.amount:,.2f} — {self.invoice.student.full_name} ({self.paid_date})"

    def clean(self):
        """
        Allow instalment payments. Rules:
        - Amount must be positive.
        - New payment must not push total paid above the invoice amount.
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
        total_paid = (
            Payment.objects
            .filter(invoice=self.invoice)
            .aggregate(total=Sum("amount"))["total"]
        ) or 0
        Invoice.objects.filter(pk=self.invoice.pk).update(amount_paid=total_paid)
        self.invoice.amount_paid = total_paid
        self.invoice.update_status()


class CreditNote(models.Model):
    """Manually logged student overpayments or credit balances."""
    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student    = models.ForeignKey("school.Student", on_delete=models.CASCADE, related_name="credit_notes")
    amount     = models.DecimalField(max_digits=12, decimal_places=2)
    reference  = models.CharField(max_length=100)
    notes      = models.TextField(blank=True)
    is_used    = models.BooleanField(default=False)
    logged_by  = models.ForeignKey("school.User", on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "credit_notes"
        ordering = ["-created_at"]
        indexes = [
            GinIndex(
                name='credit_search_idx',
                fields=['reference', 'notes'],
                opclasses=['gin_trgm_ops', 'gin_trgm_ops']
            )
        ]

    def __str__(self):
        return f"Credit Note: ₦{self.amount:,.2f} — {self.student.full_name}"


class Expenditure(models.Model):
    """
    Money spent by the school.
    """
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

    id           = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    date         = models.DateField(help_text="Date the expenditure occurred")
    category     = models.CharField(max_length=20, choices=CATEGORY)
    description  = models.CharField(max_length=300)
    amount       = models.DecimalField(max_digits=12, decimal_places=2)
    reference    = models.CharField(max_length=100, blank=True,
                                    help_text="Receipt number, invoice ref, or bank reference")
    notes        = models.TextField(blank=True)
    recorded_by  = models.ForeignKey(
        "school.User", on_delete=models.SET_NULL, null=True,
        related_name="expenditures_recorded",
    )
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "expenditures"
        ordering = ["-date", "-created_at"]
        indexes = [
            models.Index(fields=["date"],     name="expenditure_date_idx"),
            models.Index(fields=["category"], name="expenditure_cat_idx"),
            GinIndex(
                name='expenditure_search_idx',
                fields=['description', 'reference'],
                opclasses=['gin_trgm_ops', 'gin_trgm_ops']
            )
        ]

    def __str__(self):
        return f"{self.get_category_display()}: ₦{self.amount:,.2f} — {self.date}"