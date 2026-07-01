from rest_framework.test import APITestCase
from rest_framework import status
from django.contrib.auth import get_user_model
from django.urls import reverse

from school.models import Expenditure

User = get_user_model()


class ExpenditureViewSetTests(APITestCase):
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

        self.expenditure1 = Expenditure.objects.create(
            amount=200.00, category="maintenance", date="2026-06-01",
            description="Plumbing repair", recorded_by=self.admin_user,
        )
        self.expenditure2 = Expenditure.objects.create(
            amount=50.00, category="supplies", date="2026-06-15",
            description="Stationery order", recorded_by=self.admin_user,
        )

        self.list_url = reverse("expenditure-list")
        self.summary_url = reverse("expenditure-summary")

    def _detail_url(self, pk):
        return reverse("expenditure-detail", args=[pk])

    # --- list / queryset visibility ---------------------------------

    def test_parent_sees_no_expenditures(self):
        self.client.force_authenticate(user=self.parent_user)
        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 0)

    def test_admin_sees_all_expenditures(self):
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 2)

    def test_unauthenticated_user_is_rejected(self):
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    # --- filtering ----------------------------------------------------

    def test_filter_by_category(self):
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(self.list_url, {"category": "supplies"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["category"], "supplies")

    def test_filter_by_date_range(self):
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(
            self.list_url, {"date_from": "2026-06-10", "date_to": "2026-06-30"}
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["category"], "supplies")

    def test_search_by_description(self):
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(self.list_url, {"search": "Plumbing"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["category"], "maintenance")

    # --- create permissions -------------------------------------------

    def test_admin_can_create_expenditure(self):
        self.client.force_authenticate(user=self.admin_user)
        payload = {
            "amount": "75.00",
            "category": "transport",
            "date": "2026-06-20",
            "description": "Fuel for school bus",
        }
        response = self.client.post(self.list_url, payload)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["recorded_by"], self.admin_user.pk)

    def test_editor_can_create_expenditure(self):
        self.client.force_authenticate(user=self.editor_user)
        payload = {
            "amount": "30.00",
            "category": "events",
            "date": "2026-06-22",
            "description": "Sports day banners",
        }
        response = self.client.post(self.list_url, payload)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["recorded_by"], self.editor_user.pk)

    def test_parent_cannot_create_expenditure(self):
        self.client.force_authenticate(user=self.parent_user)
        payload = {
            "amount": "30.00",
            "category": "events",
            "date": "2026-06-22",
            "description": "Should not be allowed",
        }
        response = self.client.post(self.list_url, payload)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(Expenditure.objects.count(), 2)

    # --- delete permissions ---------------------------------------------

    def test_admin_can_delete_expenditure(self):
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.delete(self._detail_url(self.expenditure1.pk))

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Expenditure.objects.filter(pk=self.expenditure1.pk).exists())

    def test_editor_cannot_delete_expenditure(self):
        self.client.force_authenticate(user=self.editor_user)
        response = self.client.delete(self._detail_url(self.expenditure1.pk))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(Expenditure.objects.filter(pk=self.expenditure1.pk).exists())

    def test_parent_cannot_delete_expenditure(self):
        self.client.force_authenticate(user=self.parent_user)
        response = self.client.delete(self._detail_url(self.expenditure1.pk))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(Expenditure.objects.filter(pk=self.expenditure1.pk).exists())

    # --- summary endpoint -----------------------------------------------

    def test_expenditure_summary_aggregation(self):
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(self.summary_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total_spent"], 250.00)
        self.assertEqual(response.data["count"], 2)
        categories = [item["category"] for item in response.data["by_category"]]
        self.assertIn("maintenance", categories)
        self.assertIn("supplies", categories)

    def test_summary_respects_date_filter(self):
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(
            self.summary_url, {"date_from": "2026-06-10", "date_to": "2026-06-30"}
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total_spent"], 50.00)
        self.assertEqual(response.data["count"], 1)

    def test_summary_empty_for_parent(self):
        self.client.force_authenticate(user=self.parent_user)
        response = self.client.get(self.summary_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total_spent"], 0)
        self.assertEqual(response.data["count"], 0)
        self.assertEqual(response.data["by_category"], [])

    def test_unauthenticated_summary_is_rejected(self):
        response = self.client.get(self.summary_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)