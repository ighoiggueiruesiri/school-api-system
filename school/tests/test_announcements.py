from rest_framework.test import APITestCase
from rest_framework import status
from django.contrib.auth import get_user_model
from django.urls import reverse

from school.models import Announcement

User = get_user_model()


class AnnouncementViewSetTests(APITestCase):
    def setUp(self):
        self.admin_user = User.objects.create_user(
            email="admin@example.com", password="Password123", role="admin"
        )
        self.teacher_user = User.objects.create_user(
            email="teacher@example.com", password="Password123", role="teacher"
        )
        self.parent_user = User.objects.create_user(
            email="parent@example.com", password="Password123", role="parent"
        )

        self.announcement_all = Announcement.objects.create(
            title="School Closed", body="Snow day.", audience="all", author=self.admin_user
        )
        self.announcement_parents = Announcement.objects.create(
            title="PTA Meeting", body="Join us.", audience="parents", author=self.admin_user
        )
        # FIX: was audience="staff" which is not a valid model choice.
        # Valid choices are: "all", "parents", "teachers".
        self.announcement_teachers = Announcement.objects.create(
            title="Staff Meeting", body="Mandatory.", audience="teachers", author=self.admin_user
        )

        self.list_url   = reverse("announcements-list")
        self.detail_url = reverse("announcements-detail", kwargs={"pk": self.announcement_all.id})
        self.teachers_detail_url = reverse(
            "announcements-detail", kwargs={"pk": self.announcement_teachers.id}
        )

    # ------------------------------------------------------------------ #
    # Authentication
    # ------------------------------------------------------------------ #

    def test_unauthenticated_user_cannot_list(self):
        """Unauthenticated requests must be rejected with 401."""
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_unauthenticated_user_cannot_create(self):
        """Unauthenticated POST must be rejected with 401."""
        data = {"title": "Hack", "body": "...", "audience": "all"}
        response = self.client.post(self.list_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    # ------------------------------------------------------------------ #
    # Audience filtering — list
    # ------------------------------------------------------------------ #

    def test_parent_sees_only_all_and_parents_announcements(self):
        """Parents only see 'all' and 'parents' audience announcements."""
        self.client.force_authenticate(user=self.parent_user)
        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        titles = [item["title"] for item in response.data["results"]]
        self.assertIn("School Closed", titles)
        self.assertIn("PTA Meeting", titles)
        self.assertNotIn("Staff Meeting", titles)
        self.assertEqual(len(titles), 2)

    def test_teacher_sees_all_announcements(self):
        """Teachers (staff) receive the unfiltered queryset."""
        self.client.force_authenticate(user=self.teacher_user)
        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 3)

    def test_admin_sees_all_announcements(self):
        """Admins receive the unfiltered queryset."""
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 3)

    # ------------------------------------------------------------------ #
    # Audience filtering — retrieve (detail)
    # ------------------------------------------------------------------ #

    def test_parent_cannot_retrieve_teachers_announcement(self):
        """
        A parent hitting GET /announcements/{id}/ for a teachers-only announcement
        must receive 404 (excluded from their queryset, not merely forbidden).
        """
        self.client.force_authenticate(user=self.parent_user)
        response = self.client.get(self.teachers_detail_url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_teacher_can_retrieve_teachers_announcement(self):
        """Teachers can retrieve a teachers-audience announcement."""
        self.client.force_authenticate(user=self.teacher_user)
        response = self.client.get(self.teachers_detail_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    # ------------------------------------------------------------------ #
    # Create
    # ------------------------------------------------------------------ #

    def test_teacher_can_create_announcement(self):
        """Teachers (staff) can POST new announcements."""
        self.client.force_authenticate(user=self.teacher_user)
        data = {"title": "Field Trip", "body": "Bring lunch.", "audience": "all"}
        response = self.client.post(self.list_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_admin_can_create_announcement(self):
        """Admins can also POST new announcements."""
        self.client.force_authenticate(user=self.admin_user)
        data = {"title": "Holiday", "body": "No school.", "audience": "all"}
        response = self.client.post(self.list_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_author_is_set_automatically_on_create(self):
        """The author field must be set to the requesting user, not from request body."""
        self.client.force_authenticate(user=self.teacher_user)
        data = {
            "title": "Auto-author test",
            "body": "Body.",
            "audience": "all",
            "author": self.admin_user.id,  # should be ignored
        }
        response = self.client.post(self.list_url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        created = Announcement.objects.get(title="Auto-author test")
        self.assertEqual(created.author, self.teacher_user)

    def test_parent_cannot_create_announcement(self):
        """
        Parents must be blocked from POST with 403.
        Requires perform_create to raise DRF's PermissionDenied (not the
        built-in PermissionError which DRF does not catch and returns 500).
        """
        self.client.force_authenticate(user=self.parent_user)
        data = {"title": "Spam", "body": "Spam.", "audience": "all"}
        response = self.client.post(self.list_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    # ------------------------------------------------------------------ #
    # Update (PUT / PATCH)
    # ------------------------------------------------------------------ #

    def test_teacher_can_update_announcement(self):
        """Teachers (staff) may PUT/PATCH existing announcements."""
        self.client.force_authenticate(user=self.teacher_user)
        data = {"title": "Updated Title", "body": "Updated body.", "audience": "all"}
        response = self.client.put(self.detail_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.announcement_all.refresh_from_db()
        self.assertEqual(self.announcement_all.title, "Updated Title")

    def test_teacher_can_partial_update_announcement(self):
        """Teachers may PATCH a subset of fields."""
        self.client.force_authenticate(user=self.teacher_user)
        response = self.client.patch(self.detail_url, {"title": "Patched"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.announcement_all.refresh_from_db()
        self.assertEqual(self.announcement_all.title, "Patched")

    def test_parent_cannot_update_announcement(self):
        """Parents must be blocked from PUT with 403."""
        self.client.force_authenticate(user=self.parent_user)
        data = {"title": "Hacked", "body": "Hacked.", "audience": "all"}
        response = self.client.put(self.detail_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_parent_cannot_partial_update_announcement(self):
        """Parents must be blocked from PATCH with 403."""
        self.client.force_authenticate(user=self.parent_user)
        response = self.client.patch(self.detail_url, {"title": "Hacked"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_update_announcement(self):
        """Admins (also staff) may update announcements."""
        self.client.force_authenticate(user=self.admin_user)
        data = {"title": "Admin Updated", "body": "New body.", "audience": "all"}
        response = self.client.put(self.detail_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    # ------------------------------------------------------------------ #
    # Delete
    # ------------------------------------------------------------------ #

    def test_admin_can_delete_announcement(self):
        """Admins must be able to delete any announcement."""
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.delete(self.detail_url)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Announcement.objects.filter(pk=self.announcement_all.pk).exists())

    def test_teacher_cannot_delete_announcement(self):
        """Teachers are staff but not admins — DELETE must return 403."""
        self.client.force_authenticate(user=self.teacher_user)
        response = self.client.delete(self.detail_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_parent_cannot_delete_announcement(self):
        """Parents must also be blocked from DELETE."""
        self.client.force_authenticate(user=self.parent_user)
        response = self.client.delete(self.detail_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    # ------------------------------------------------------------------ #
    # Search
    # ------------------------------------------------------------------ #

    def test_search_filters_by_title(self):
        """The search filter must narrow results by title."""
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(self.list_url, {"search": "PTA"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["title"], "PTA Meeting")

    def test_search_filters_by_body(self):
        """The search filter must also match against body text."""
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(self.list_url, {"search": "Mandatory"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["title"], "Staff Meeting")

    def test_search_respects_audience_filter_for_parents(self):
        """
        A parent searching must still only see results from their allowed
        audience — search must not bypass the queryset filter.
        """
        self.client.force_authenticate(user=self.parent_user)
        # "Mandatory" belongs to a teachers-only announcement
        response = self.client.get(self.list_url, {"search": "Mandatory"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 0)