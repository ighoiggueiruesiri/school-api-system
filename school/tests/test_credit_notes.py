from rest_framework.test import APITestCase
from rest_framework import status
from django.contrib.auth import get_user_model
from django.urls import reverse

from school.models import CreditNote, Student

User = get_user_model()


class CreditNoteViewSetTests(APITestCase):
    def setUp(self):
        self.admin_user = User.objects.create_user(
            email="admin@example.com", password="Password123", role="admin"
        )
        self.editor_user = User.objects.create_user(
            email="editor@example.com", password="Password123", role="editor"
        )
        self.parent_user = User.objects.create_user(
            email="parent@example.com", password="Password123", role="parent"
        )
        self.other_parent_user = User.objects.create_user(
            email="parent2@example.com", password="Password123", role="parent"
        )

        # date_of_birth is a required (non-null) field on Student, and
        # admission_number is required + unique, so both must be supplied
        # explicitly and be distinct across the two students created here.
        self.student = Student.objects.create(
            first_name="Jane",
            last_name="Doe",
            admission_number="ADM-0001",
            date_of_birth="2015-04-12",
            gender="female",
        )
        self.student.parents.add(self.parent_user)

        self.other_student = Student.objects.create(
            first_name="Stranger",
            last_name="Kid",
            admission_number="ADM-0002",
            date_of_birth="2016-09-30",
            gender="male",
        )
        self.other_student.parents.add(self.other_parent_user)

        self.credit_note = CreditNote.objects.create(
            student=self.student,
            amount=50.00,
            reference="CR-001",
            logged_by=self.admin_user,
        )
        self.other_credit_note = CreditNote.objects.create(
            student=self.other_student,
            amount=10.00,
            reference="CR-002",
            logged_by=self.admin_user,
        )

        self.list_url = reverse("credit-notes-list")
        self.detail_url = reverse("credit-notes-detail", kwargs={"pk": self.credit_note.id})
        self.other_detail_url = reverse("credit-notes-detail", kwargs={"pk": self.other_credit_note.id})

    # ---- List / scoping ----

    def test_parent_sees_only_own_childs_credit_notes(self):
        """Parents should only see credit notes belonging to their own children."""
        self.client.force_authenticate(user=self.parent_user)
        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["reference"], "CR-001")

    def test_parent_cannot_retrieve_other_childs_credit_note(self):
        """A parent should get a 404 (filtered out of queryset) for another family's note."""
        self.client.force_authenticate(user=self.parent_user)
        response = self.client.get(self.other_detail_url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_admin_sees_all_credit_notes(self):
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 2)

    def test_admin_can_filter_by_student(self):
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(self.list_url, {"student": str(self.student.id)})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["reference"], "CR-001")

    def test_search_filter_matches_reference(self):
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(self.list_url, {"search": "CR-002"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["reference"], "CR-002")

    # ---- Create ----

    def test_editor_can_create_credit_note(self):
        self.client.force_authenticate(user=self.editor_user)
        data = {
            "student": self.student.id,
            "amount": 100.00,
            "reference": "CR-003",
        }

        response = self.client.post(self.list_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(CreditNote.objects.count(), 3)

    def test_admin_can_create_credit_note(self):
        self.client.force_authenticate(user=self.admin_user)
        data = {
            "student": self.student.id,
            "amount": 25.00,
            "reference": "CR-004",
        }

        response = self.client.post(self.list_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_parent_cannot_create_credit_note(self):
        """Non-staff users should be blocked with a 403, not an unhandled error."""
        self.client.force_authenticate(user=self.parent_user)
        data = {"student": self.student.id, "amount": 100.00}

        response = self.client.post(self.list_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(CreditNote.objects.count(), 2)

    def test_unauthenticated_user_cannot_create_credit_note(self):
        data = {"student": self.student.id, "amount": 100.00, "reference": "CR-005"}
        response = self.client.post(self.list_url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    # ---- Delete ----

    def test_admin_can_delete_credit_note(self):
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.delete(self.detail_url)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(CreditNote.objects.filter(id=self.credit_note.id).exists())

    def test_editor_cannot_delete_credit_note(self):
        self.client.force_authenticate(user=self.editor_user)
        response = self.client.delete(self.detail_url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(CreditNote.objects.filter(id=self.credit_note.id).exists())

    def test_parent_cannot_delete_credit_note(self):
        self.client.force_authenticate(user=self.parent_user)
        response = self.client.delete(self.detail_url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(CreditNote.objects.filter(id=self.credit_note.id).exists())