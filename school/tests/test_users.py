from rest_framework.test import APITestCase
from rest_framework import status
from django.contrib.auth import get_user_model
from django.urls import reverse # <-- Add this import

User = get_user_model()

class UserViewSetTests(APITestCase):
    def setUp(self):
        self.admin_user = User.objects.create_user(
            email="admin@example.com",
            password="AdminPassword123",
            first_name="Admin",
            last_name="User",
            role="admin"
        )
        
        self.parent_user = User.objects.create_user(
            email="parent@example.com",
            password="ParentPassword123",
            first_name="Parent",
            last_name="User",
            role="parent"
        )

        self.editor_user = User.objects.create_user(
            email="editor@example.com",
            password="EditorPassword123",
            first_name="Editor",
            last_name="User",
            role="editor"
        )

        self.teacher_user = User.objects.create_user(
            email="teacher2@example.com",
            password="TeacherPassword123",
            first_name="Teacher",
            last_name="User",
            role="teacher"
        )

        # Use reverse to get the list URL for the viewset
        self.users_list_url = reverse("users-list")

    def test_list_users_with_role_filter(self):
        """Test GET users returns paginated data and filters by role."""
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(self.users_list_url + "?role=parent")
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("count", response.data)
        self.assertIn("pages", response.data)
        self.assertIn("results", response.data)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["email"], self.parent_user.email)

    def test_admin_can_create_staff_user(self):
        """Test that an admin can create an editor/teacher/non_academic account."""
        self.client.force_authenticate(user=self.admin_user)
        data = {
            "email": "teacher@example.com",
            "first_name": "Test",
            "last_name": "Teacher",
            "role": "teacher"
        }
        response = self.client.post(self.users_list_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        new_user = User.objects.get(email="teacher@example.com")
        self.assertTrue(new_user.check_password("ChangeMe123"))

    def test_non_admin_cannot_create_user(self):
        """Test that non-admins are forbidden from creating user accounts."""
        self.client.force_authenticate(user=self.parent_user)
        data = {
            "email": "hacker@example.com",
            "first_name": "Hacker",
            "last_name": "User",
            "role": "editor"
        }
        response = self.client.post(self.users_list_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data["error"], "Only admins can create user accounts.")

    def test_admin_can_deactivate_user(self):
        """Test DELETE users/<id>/ deactivates (soft deletes) the user."""
        self.client.force_authenticate(user=self.admin_user)
        
        # Use reverse to dynamically build the URL with the specific user ID
        delete_url = reverse("users-detail", kwargs={"pk": self.parent_user.id})
        
        response = self.client.delete(delete_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["message"], "User deactivated.")
        
        self.parent_user.refresh_from_db()
        self.assertFalse(self.parent_user.is_active)

    def test_non_admin_cannot_deactivate_user(self):
        """Test that non-admins cannot deactivate user accounts."""
        self.client.force_authenticate(user=self.parent_user)
        
        # Use reverse to dynamically build the URL with the specific user ID
        delete_url = reverse("users-detail", kwargs={"pk": self.admin_user.id})
        
        response = self.client.delete(delete_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data["error"], "Only admins can deactivate accounts.")

    def test_editor_can_list_all_users(self):
        """Editors have full read access, same as admins."""
        self.client.force_authenticate(user=self.editor_user)
        response = self.client.get(self.users_list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        returned_emails = {u["email"] for u in response.data["results"]}
        self.assertIn(self.admin_user.email, returned_emails)
        self.assertIn(self.parent_user.email, returned_emails)
        self.assertIn(self.teacher_user.email, returned_emails)

    def test_parent_listing_users_only_sees_self(self):
        """A non-admin/editor user (e.g. parent) should only see their own record."""
        self.client.force_authenticate(user=self.parent_user)
        response = self.client.get(self.users_list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["email"], self.parent_user.email)

    def test_teacher_listing_users_only_sees_self(self):
        """Same self-only scoping applies to teacher/non_academic roles."""
        self.client.force_authenticate(user=self.teacher_user)
        response = self.client.get(self.users_list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["email"], self.teacher_user.email)

    def test_parent_can_retrieve_own_profile(self):
        """A parent can fetch their own user record."""
        self.client.force_authenticate(user=self.parent_user)
        url = reverse("users-detail", kwargs={"pk": self.parent_user.id})

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["email"], self.parent_user.email)

    def test_parent_cannot_retrieve_other_users_profile(self):
        """A parent requesting another user's id should get a 404, not their data."""
        self.client.force_authenticate(user=self.parent_user)
        url = reverse("users-detail", kwargs={"pk": self.admin_user.id})

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_admin_can_retrieve_any_users_profile(self):
        """Admins can fetch any user's record by id."""
        self.client.force_authenticate(user=self.admin_user)
        url = reverse("users-detail", kwargs={"pk": self.parent_user.id})

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["email"], self.parent_user.email)

    def test_parent_can_update_own_profile(self):
        """A parent can edit their own first/last name."""
        self.client.force_authenticate(user=self.parent_user)
        url = reverse("users-detail", kwargs={"pk": self.parent_user.id})

        response = self.client.patch(url, {"first_name": "Updated"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.parent_user.refresh_from_db()
        self.assertEqual(self.parent_user.first_name, "Updated")

    def test_parent_cannot_update_other_users_profile(self):
        """A parent should not be able to edit another user's record at all."""
        self.client.force_authenticate(user=self.parent_user)
        url = reverse("users-detail", kwargs={"pk": self.admin_user.id})

        response = self.client.patch(url, {"first_name": "Hijacked"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.admin_user.refresh_from_db()
        self.assertNotEqual(self.admin_user.first_name, "Hijacked")