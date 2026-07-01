from rest_framework.test import APITestCase
from rest_framework import status
from django.contrib.auth import get_user_model
from django.urls import reverse

User = get_user_model()


class AuthAPITests(APITestCase):
    """
    Tests for:
        POST   /api/register/
        POST   /api/login/
        POST   /api/logout/
        GET    /api/me/
        PATCH  /api/me/
    """

    def setUp(self):
        self.user_email    = "testuser@example.com"
        self.user_password = "StrongPassword123"
        self.user = User.objects.create_user(
            email      = self.user_email,
            password   = self.user_password,
            first_name = "Test",
            last_name  = "User",
            role       = "parent",
        )

        self.register_url = reverse("register")
        self.login_url    = reverse("login")
        self.logout_url   = reverse("logout")
        self.me_url       = reverse("me")

    # ── helpers ───────────────────────────────────────────────────────────────

    def _login(self, email=None, password=None):
        """Return the raw login response (tokens in .data)."""
        return self.client.post(self.login_url, {
            "email":    email    or self.user_email,
            "password": password or self.user_password,
        })

    def _auth_header(self, access_token):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")

    # =========================================================================
    # REGISTER
    # =========================================================================

    def test_register_parent_succeeds(self):
        """Valid payload creates a parent account and returns 201."""
        data = {
            "email":      "newparent@example.com",
            "password":   "NewPassword123",
            "first_name": "New",
            "last_name":  "Parent",
            "role":       "parent",
        }
        response = self.client.post(self.register_url, data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["message"], "Account created. You can now log in.")
        self.assertEqual(response.data["email"], data["email"])
        self.assertTrue(User.objects.filter(email=data["email"]).exists())

    def test_register_forces_parent_role(self):
        """
        RegisterSerializer hard-codes role='parent' regardless of what the
        client sends — confirm an 'admin' role attempt is silently ignored.
        """
        data = {
            "email":      "notadmin@example.com",
            "password":   "Password123",
            "first_name": "Not",
            "last_name":  "Admin",
            "role":       "admin",   # should be ignored
        }
        self.client.post(self.register_url, data)
        user = User.objects.get(email="notadmin@example.com")
        self.assertEqual(user.role, "parent")

    def test_register_duplicate_email_returns_400(self):
        """Attempting to register an already-used email must fail with 400."""
        data = {
            "email":      self.user_email,   # already exists
            "password":   "AnotherPass123",
            "first_name": "Dupe",
            "last_name":  "User",
        }
        response = self.client.post(self.register_url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_missing_required_fields_returns_400(self):
        """Omitting required fields (first_name, last_name) must fail with 400."""
        data = {"email": "incomplete@example.com", "password": "Password123"}
        response = self.client.post(self.register_url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_optional_phone_field(self):
        """Supplying an optional phone field should succeed."""
        data = {
            "email":      "withphone@example.com",
            "password":   "Password123",
            "first_name": "Has",
            "last_name":  "Phone",
            "phone":      "+2348012345678",
        }
        response = self.client.post(self.register_url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(email="withphone@example.com")
        self.assertEqual(user.phone, "+2348012345678")

    # =========================================================================
    # LOGIN
    # =========================================================================

    def test_login_returns_access_and_refresh_tokens(self):
        """Valid credentials return 200 with both JWT tokens."""
        response = self._login()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access",  response.data)
        self.assertIn("refresh", response.data)

    def test_login_response_includes_user_payload(self):
        """
        LoginSerializer.validate() embeds a 'user' dict with id, email,
        full_name, and role — assert all four keys are present.
        """
        response = self._login()
        self.assertIn("user", response.data)
        for key in ("id", "email", "full_name", "role"):
            self.assertIn(key, response.data["user"])

    def test_login_wrong_password_returns_401(self):
        """Incorrect password must be rejected with 401."""
        response = self._login(password="WrongPassword!")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_login_unknown_email_returns_401(self):
        """Non-existent email must be rejected with 401."""
        response = self._login(email="ghost@example.com")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    # =========================================================================
    # LOGOUT
    # =========================================================================

    def test_logout_blacklists_refresh_token(self):
        """Logout with a valid refresh token returns 200 and blacklists it."""
        login_resp    = self._login()
        refresh_token = login_resp.data["refresh"]
        access_token  = login_resp.data["access"]

        self._auth_header(access_token)
        response = self.client.post(self.logout_url, {"refresh": refresh_token})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["message"], "Logged out.")

    def test_logout_reuse_of_blacklisted_token_returns_400(self):
        """Re-submitting an already-blacklisted token must return 400."""
        login_resp    = self._login()
        refresh_token = login_resp.data["refresh"]
        access_token  = login_resp.data["access"]

        self._auth_header(access_token)
        self.client.post(self.logout_url, {"refresh": refresh_token})   # first logout

        response = self.client.post(self.logout_url, {"refresh": refresh_token})  # reuse
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_logout_without_refresh_token_returns_400(self):
        """
        Posting to logout with no body must return 400 (KeyError on
        request.data["refresh"] is caught and returns {"error": ...}).
        """
        login_resp = self._login()
        self._auth_header(login_resp.data["access"])
        response = self.client.post(self.logout_url, {})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_logout_requires_authentication(self):
        """Unauthenticated call to logout must return 401."""
        self.client.credentials()   # clear any auth
        response = self.client.post(self.logout_url, {"refresh": "sometoken"})
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    # =========================================================================
    # ME — GET
    # =========================================================================

    def test_me_get_returns_authenticated_user(self):
        """GET /me/ returns the profile of the logged-in user."""
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.me_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["email"], self.user_email)

    def test_me_get_returns_expected_fields(self):
        """GET /me/ response contains all fields declared in UserSerializer."""
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.me_url)
        expected_fields = {
            "id", "email", "first_name", "last_name",
            "phone", "role", "profile_photo",
            "date_joined", "is_active", "staff_profile",
        }
        self.assertTrue(expected_fields.issubset(response.data.keys()))

    def test_me_get_requires_authentication(self):
        """Unauthenticated GET /me/ must return 401."""
        self.client.credentials()
        response = self.client.get(self.me_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    # =========================================================================
    # ME — PATCH
    # =========================================================================

    def test_me_patch_updates_first_name(self):
        """PATCH /me/ with first_name persists the change."""
        self.client.force_authenticate(user=self.user)
        response = self.client.patch(self.me_url, {"first_name": "UpdatedName"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["first_name"], "UpdatedName")
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "UpdatedName")

    def test_me_patch_read_only_role_is_ignored(self):
        """
        role is declared read_only in UserSerializer — attempting to change it
        via PATCH must be silently ignored and the original role preserved.
        """
        self.client.force_authenticate(user=self.user)
        response = self.client.patch(self.me_url, {"role": "admin"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.role, "parent")   # unchanged

    def test_me_patch_requires_authentication(self):
        """Unauthenticated PATCH /me/ must return 401."""
        self.client.credentials()
        response = self.client.patch(self.me_url, {"first_name": "Hacker"})
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_me_patch_partial_update_does_not_clear_other_fields(self):
        """
        Patching one field must leave unrelated fields intact (standard
        partial=True behaviour in DRF).
        """
        self.client.force_authenticate(user=self.user)
        self.client.patch(self.me_url, {"first_name": "Only"})
        self.user.refresh_from_db()
        # last_name was set in setUp and must be untouched
        self.assertEqual(self.user.last_name, "User")

    def test_me_patch_staff_profile_ignored_for_parent(self):
        """
        UserSerializer.update() only creates/updates StaffProfile for
        teacher/non_academic roles — a parent sending staff_profile data
        must get 200 but no StaffProfile row created.
        """
        from school.models import StaffProfile   # adjust import path as needed
        self.client.force_authenticate(user=self.user)
        payload = {"staff_profile": {"highest_qualification": "MSc"}}
        response = self.client.patch(self.me_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(StaffProfile.objects.filter(user=self.user).exists())

    def test_me_patch_staff_profile_for_teacher(self):
        """
        A teacher patching /me/ with staff_profile data must have a
        StaffProfile row created/updated via update_or_create.
        """
        from school.models import StaffProfile   # adjust import path as needed
        teacher = User.objects.create_user(
            email      = "teacher@example.com",
            password   = "TeacherPass123",
            first_name = "Jane",
            last_name  = "Doe",
            role       = "teacher",
        )
        self.client.force_authenticate(user=teacher)
        payload = {"staff_profile": {"highest_qualification": "B.Ed", "nationality": "Nigerian"}}
        response = self.client.patch(self.me_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        profile = StaffProfile.objects.get(user=teacher)
        self.assertEqual(profile.highest_qualification, "B.Ed")