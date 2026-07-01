from rest_framework.test import APITestCase
from rest_framework import status
from django.contrib.auth import get_user_model
from django.urls import reverse

from school.models import Inquiry

User = get_user_model()


class InquiryViewSetTests(APITestCase):
    """
    Tests for InquiryViewSet.

    Permissions:
      - POST   (create)  → AllowAny
      - GET    (list)    → IsAuthenticated
      - GET    (detail)  → IsAuthenticated
      - PUT    (update)  → IsAuthenticated
      - PATCH  (partial) → IsAuthenticated
      - DELETE (destroy) → IsAuthenticated
    """

    def setUp(self):
        self.admin_user = User.objects.create_user(
            email="admin@example.com", password="Password123", role="admin"
        )
        self.list_url = reverse("inquiries-list")

        # Removed non-existent `message` field — model only has:
        # parent_name, email, phone, interested_class, created_at
        self.inquiry = Inquiry.objects.create(
            parent_name="John Doe",
            email="john@example.com",
            phone="1234567890",
            interested_class="Grade 1",
        )

    def _detail_url(self, pk):
        return reverse("inquiries-detail", kwargs={"pk": pk})

    # ------------------------------------------------------------------ #
    # CREATE — public                                                       #
    # ------------------------------------------------------------------ #

    def test_unauthenticated_user_can_submit_inquiry(self):
        """Anonymous users can POST a new lead."""
        data = {
            "parent_name": "Jane Smith",
            "email": "jane@example.com",
            "phone": "0987654321",
            "interested_class": "Grade 2",
        }
        response = self.client.post(self.list_url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Inquiry.objects.count(), 2)
        # Serializer exposes id, parent_name, email, phone, interested_class, created_at
        self.assertEqual(response.data["parent_name"], "Jane Smith")
        self.assertEqual(response.data["email"], "jane@example.com")
        self.assertIn("id", response.data)
        self.assertIn("created_at", response.data)

    def test_create_with_minimal_fields(self):
        """interested_class is optional (blank=True); minimal payload should succeed."""
        data = {
            "parent_name": "No Class",
            "email": "noclass@example.com",
            "phone": "1112223333",
        }
        response = self.client.post(self.list_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_create_missing_required_field_returns_400(self):
        """A POST without a required field (email) must return 400."""
        data = {
            "parent_name": "No Email",
            "phone": "0000000000",
        }
        response = self.client.post(self.list_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", response.data)

    # ------------------------------------------------------------------ #
    # READ — authenticated only                                            #
    # ------------------------------------------------------------------ #

    def test_unauthenticated_user_cannot_list_inquiries(self):
        """Anonymous users must receive 401 on GET list."""
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_authenticated_user_can_list_inquiries(self):
        """Authenticated users receive a paginated list of inquiries."""
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # DynamicPageSizePagination wraps results in {"results": [...], ...}
        self.assertIn("results", response.data)
        self.assertEqual(len(response.data["results"]), 1)

    def test_unauthenticated_user_cannot_retrieve_inquiry(self):
        """Anonymous users must receive 401 on GET detail."""
        response = self.client.get(self._detail_url(self.inquiry.pk))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_authenticated_user_can_retrieve_inquiry(self):
        """Authenticated users can fetch a single inquiry by PK."""
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(self._detail_url(self.inquiry.pk))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["email"], "john@example.com")

    # ------------------------------------------------------------------ #
    # UPDATE                                                               #
    # ------------------------------------------------------------------ #

    def test_unauthenticated_user_cannot_update_inquiry(self):
        """Anonymous PUT must return 401."""
        data = {
            "parent_name": "Hacker",
            "email": "hack@example.com",
            "phone": "0000000000",
        }
        response = self.client.put(self._detail_url(self.inquiry.pk), data, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_authenticated_user_can_update_inquiry(self):
        """Authenticated users can PUT a full update."""
        self.client.force_authenticate(user=self.admin_user)
        data = {
            "parent_name": "John Updated",
            "email": "updated@example.com",
            "phone": "9999999999",
            "interested_class": "Grade 3",
        }
        response = self.client.put(self._detail_url(self.inquiry.pk), data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["parent_name"], "John Updated")

    def test_authenticated_user_can_partial_update_inquiry(self):
        """Authenticated users can PATCH individual fields."""
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.patch(
            self._detail_url(self.inquiry.pk),
            {"interested_class": "Grade 5"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["interested_class"], "Grade 5")

    # ------------------------------------------------------------------ #
    # DELETE                                                               #
    # ------------------------------------------------------------------ #

    def test_unauthenticated_user_cannot_delete_inquiry(self):
        """Anonymous DELETE must return 401."""
        response = self.client.delete(self._detail_url(self.inquiry.pk))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(Inquiry.objects.count(), 1)

    def test_authenticated_user_can_delete_inquiry(self):
        """Authenticated users can delete an inquiry."""
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.delete(self._detail_url(self.inquiry.pk))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(Inquiry.objects.count(), 0)

    # ------------------------------------------------------------------ #
    # SEARCH                                                               #
    # ------------------------------------------------------------------ #

    def test_search_by_parent_name(self):
        """The ?search= filter works on parent_name."""
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(self.list_url, {"search": "John"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)

    def test_search_no_match_returns_empty(self):
        """A search with no matching records returns an empty list."""
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(self.list_url, {"search": "zzznomatch"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 0)