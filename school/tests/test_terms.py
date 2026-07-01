from rest_framework.test import APITestCase
from rest_framework import status
from django.contrib.auth import get_user_model
from django.urls import reverse

# Adjust the import path to your models
from school.models import Term

User = get_user_model()


class TermViewSetTests(APITestCase):
    def setUp(self):
        self.admin_user = User.objects.create_user(
            email="admin@example.com", password="Password123", role="admin"
        )
        self.editor_user = User.objects.create_user(
            email="editor@example.com", password="Password123", role="editor"
        )
        self.teacher_user = User.objects.create_user(
            email="teacher@example.com", password="Password123", role="teacher"
        )

        self.term = Term.objects.create(
            name="first",
            academic_year="2025/2026",
            start_date="2025-09-01",
            end_date="2025-12-15",
            is_current=True,
        )
        self.term_list_url = reverse("terms-list")
        self.term_detail_url = reverse("terms-detail", kwargs={"pk": self.term.id})

    def test_list_terms(self):
        """Test that authenticated users can list terms."""
        self.client.force_authenticate(user=self.teacher_user)
        response = self.client.get(self.term_list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("results", response.data)
        self.assertEqual(len(response.data["results"]), 1)

    def test_editor_can_create_term(self):
        """Test that an editor (or admin) can create a term."""
        self.client.force_authenticate(user=self.editor_user)
        data = {
            "name": "second",
            "academic_year": "2025/2026",
            "start_date": "2026-01-05",
            "end_date": "2026-04-03",
            "is_current": False,
        }
        response = self.client.post(self.term_list_url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Term.objects.count(), 2)

    def test_create_term_duplicate_name_and_year_rejected(self):
        """Test that the unique_together constraint on (name, academic_year) is enforced."""
        self.client.force_authenticate(user=self.admin_user)
        data = {
            "name": "first",
            "academic_year": "2025/2026",
            "start_date": "2026-05-01",
            "end_date": "2026-07-30",
            "is_current": False,
        }
        response = self.client.post(self.term_list_url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Term.objects.count(), 1)

    def test_teacher_cannot_create_term(self):
        """Test that pure teachers are forbidden from creating terms."""
        self.client.force_authenticate(user=self.teacher_user)
        data = {
            "name": "second",
            "academic_year": "2025/2026",
            "start_date": "2026-01-05",
            "end_date": "2026-04-03",
            "is_current": False,
        }
        response = self.client.post(self.term_list_url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(Term.objects.count(), 1)

    def test_setting_is_current_unsets_previous_current_term(self):
        """Test that creating/saving a term with is_current=True unsets the prior current term."""
        self.client.force_authenticate(user=self.admin_user)
        data = {
            "name": "second",
            "academic_year": "2025/2026",
            "start_date": "2026-01-05",
            "end_date": "2026-04-03",
            "is_current": True,
        }
        response = self.client.post(self.term_list_url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.term.refresh_from_db()
        self.assertFalse(self.term.is_current)

    def test_admin_can_delete_term(self):
        """Test that only admins can delete terms."""
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.delete(self.term_detail_url)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(Term.objects.count(), 0)

    def test_editor_cannot_delete_term(self):
        """Test that editors cannot delete terms (Admin only)."""
        self.client.force_authenticate(user=self.editor_user)
        response = self.client.delete(self.term_detail_url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(Term.objects.count(), 1)

    def test_get_current_term(self):
        """Test the custom action to retrieve the current term."""
        self.client.force_authenticate(user=self.teacher_user)
        current_url = reverse("terms-current")
        response = self.client.get(current_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], self.term.name)

    def test_get_current_term_when_none_set(self):
        """Test the custom action returns 404 when no term is marked current."""
        self.term.is_current = False
        self.term.save()
        self.client.force_authenticate(user=self.teacher_user)
        current_url = reverse("terms-current")
        response = self.client.get(current_url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_unauthenticated_user_cannot_list_terms(self):
        """Test that unauthenticated requests are rejected."""
        response = self.client.get(self.term_list_url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)