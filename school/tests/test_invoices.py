from datetime import date, timedelta

from rest_framework.test import APITestCase
from rest_framework import status
from django.contrib.auth import get_user_model
from django.urls import reverse

from school.models import Invoice, Student, Term

User = get_user_model()


class InvoiceViewSetTests(APITestCase):
    def setUp(self):
        self.admin_user = User.objects.create_user(
            email="admin@example.com", password="Password123", role="admin"
        )
        self.parent_user = User.objects.create_user(
            email="parent@example.com", password="Password123", role="parent"
        )

        self.term = Term.objects.create(
            name="first",
            academic_year="2026/2027",
            start_date=date.today(),
            end_date=date.today() + timedelta(days=90),
        )
        self.student = Student.objects.create(
            first_name="Kid",
            last_name="Test",
            admission_number="GSA-2026-0001",
            date_of_birth=date(2016, 1, 1),
            gender="male",
        )
        self.student.parents.add(self.parent_user)

        self.invoice = Invoice.objects.create(
            student=self.student,
            term=self.term,
            description="Fall Term Fees",
            amount=1000.00,
            amount_paid=200.00,
            status="partial",
            due_date=date.today() + timedelta(days=30),
            invoice_number="INV-MANUAL-1",
        )

        self.list_url = reverse("invoices-list")
        self.summary_url = reverse("invoices-summary")

    def test_create_invoice_generates_custom_number(self):
        """Test that an admin creating an invoice triggers the custom UUID generator."""
        self.client.force_authenticate(user=self.admin_user)
        data = {
            "student": self.student.id,
            "term": self.term.id,
            "description": "Second Term Fees",
            "amount": 500.00,
            "due_date": (date.today() + timedelta(days=30)).isoformat(),
        }

        response = self.client.post(self.list_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

        # Verify the custom logic in perform_create triggered
        self.assertIn(f"INV-{self.student.admission_number}-{self.term.id}-", response.data["invoice_number"])

    def test_parent_cannot_create_invoice(self):
        """Test that a parent (non admin/editor) cannot create an invoice."""
        self.client.force_authenticate(user=self.parent_user)
        data = {
            "student": self.student.id,
            "term": self.term.id,
            "description": "Second Term Fees",
            "amount": 500.00,
            "due_date": (date.today() + timedelta(days=30)).isoformat(),
        }

        response = self.client.post(self.list_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_parent_cannot_delete_invoice(self):
        """Test that parents/non-admins cannot delete invoices."""
        self.client.force_authenticate(user=self.parent_user)
        detail_url = reverse("invoices-detail", kwargs={"pk": self.invoice.id})

        response = self.client.delete(detail_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_parent_can_only_see_own_childs_invoices(self):
        """Test that a parent's invoice list is scoped to their own children."""
        other_parent = User.objects.create_user(
            email="other_parent@example.com", password="Password123", role="parent"
        )
        other_student = Student.objects.create(
            first_name="Other Kid",
            last_name="Test",
            admission_number="GSA-2026-0002",
            date_of_birth=date(2015, 6, 15),
            gender="female",
        )
        other_student.parents.add(other_parent)
        Invoice.objects.create(
            student=other_student,
            term=self.term,
            description="Other Kid Fees",
            amount=750.00,
            due_date=date.today() + timedelta(days=30),
            invoice_number="INV-MANUAL-2",
        )

        self.client.force_authenticate(user=self.parent_user)
        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        returned_ids = [str(item["id"]) for item in response.data["results"]]
        self.assertIn(str(self.invoice.id), returned_ids)
        self.assertEqual(len(returned_ids), 1)

    def test_invoice_summary_calculations(self):
        """Test the custom summary endpoint correctly calculates total billed, paid, and balance."""
        # Add a second unpaid invoice
        Invoice.objects.create(
            student=self.student,
            term=self.term,
            description="Extra Fees",
            amount=500.00,
            amount_paid=0,
            status="unpaid",
            due_date=date.today() + timedelta(days=30),
        )

        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(self.summary_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total_billed"], 1500.00)
        self.assertEqual(response.data["total_paid"], 200.00)
        self.assertEqual(response.data["balance"], 1300.00)
        self.assertEqual(response.data["unpaid_count"], 2)