from datetime import date

from rest_framework.test import APITestCase
from rest_framework import status
from django.contrib.auth import get_user_model
from django.urls import reverse

from school.models import Payment, Invoice, Student, Term

User = get_user_model()

class PaymentViewSetTests(APITestCase):
    def setUp(self):
        self.admin_user = User.objects.create_user(
            email="admin@example.com", password="Password123", role="admin"
        )
        self.parent_user = User.objects.create_user(
            email="parent@example.com", password="Password123", role="parent"
        )
        self.other_parent_user = User.objects.create_user(
            email="parent2@example.com", password="Password123", role="parent"
        )

        self.term = Term.objects.create(
            name="first",
            academic_year="2026/2027",
            start_date=date(2026, 9, 1),
            end_date=date(2026, 12, 15),
        )
        self.student = Student.objects.create(
            admission_number="ADM-0001",
            first_name="Kid",
            last_name="Testerson",
            date_of_birth=date(2018, 1, 1),
            gender="male",
        )
        self.student.parents.add(self.parent_user)

        self.invoice = Invoice.objects.create(
            invoice_number="INV-0001",
            student=self.student,
            term=self.term,
            description="Test Fees",
            amount=1000.00,
            due_date=date(2026, 10, 1),
        )

        self.payment = Payment.objects.create(
            invoice=self.invoice,
            amount=500.00,
            method="cash",
            paid_by=self.admin_user,
        )

        self.list_url = reverse("payments-list")
        self.detail_url = reverse("payments-detail", kwargs={"pk": self.payment.id})

    # ---- visibility ----

    def test_parent_sees_own_childs_payments(self):
        """Parents only see payments linked to their own child's invoice."""
        self.client.force_authenticate(user=self.parent_user)
        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(float(response.data["results"][0]["amount"]), 500.00)

    def test_unrelated_parent_sees_no_payments(self):
        """A parent with no children on this invoice sees an empty list, not a 403/404."""
        self.client.force_authenticate(user=self.other_parent_user)
        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 0)

    def test_admin_sees_all_payments(self):
        """Admins/editors are not filtered by parent relationship."""
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)

    # ---- create ----

    def test_admin_can_create_payment(self):
        """Admins/editors can log a payment against an invoice."""
        self.client.force_authenticate(user=self.admin_user)
        data = {
            "invoice": self.invoice.id,
            "amount": 250.00,
            "method": "bank_transfer",
            "reference": "BANK-TRANSFER-999",
        }

        response = self.client.post(self.list_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Payment.objects.count(), 2)
        # paid_by is read-only and must come from the request user, never the client
        created = Payment.objects.get(reference="BANK-TRANSFER-999")
        self.assertEqual(created.paid_by, self.admin_user)

    def test_parent_cannot_create_payment(self):
        """Parents cannot record payments, even on their own child's invoice."""
        self.client.force_authenticate(user=self.parent_user)
        data = {
            "invoice": self.invoice.id,
            "amount": 100.00,
            "method": "cash",
        }

        response = self.client.post(self.list_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(Payment.objects.count(), 1)

    def test_create_payment_exceeding_invoice_balance_is_rejected(self):
        """A payment that would exceed the invoice's remaining balance is rejected."""
        self.client.force_authenticate(user=self.admin_user)
        data = {
            "invoice": self.invoice.id,
            "amount": 600.00,  # only 500 remaining on a 1000 invoice with 500 already paid
            "method": "cash",
        }

        response = self.client.post(self.list_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Payment.objects.count(), 1)

    def test_create_payment_missing_method_is_rejected(self):
        """method is a required field (no blank=True/default on the model)."""
        self.client.force_authenticate(user=self.admin_user)
        data = {
            "invoice": self.invoice.id,
            "amount": 100.00,
        }

        response = self.client.post(self.list_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("method", response.data)

    # ---- delete ----

    def test_parent_cannot_delete_payment(self):
        """Non-admins cannot delete payment records."""
        self.client.force_authenticate(user=self.parent_user)
        response = self.client.delete(self.detail_url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(Payment.objects.count(), 1)

    def test_admin_can_delete_payment(self):
        """Admins can delete payment records."""
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.delete(self.detail_url)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(Payment.objects.count(), 0)

    def test_unauthenticated_request_is_rejected(self):
        """No auth, no access — list and create both require IsAuthenticated."""
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)