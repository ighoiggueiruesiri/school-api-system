from django.urls import reverse
from django.utils import timezone

from rest_framework import status
from rest_framework.test import APITestCase
from django.contrib.auth import get_user_model

from school.models import AuditLog

User = get_user_model()


class AuditLogViewSetTests(APITestCase):
    """
    Full test suite for AuditLogViewSet.

    Coverage map
    ────────────
    Authentication      – unauthenticated list / summary → 401
    List permissions    – non-admin → empty 200; admin → full list
    Retrieve perms      – non-admin → 404; admin → 200
    Read-only contract  – POST / PATCH / DELETE are rejected for all callers
    Filtering           – user_email, user_role, method, response_status,
                          resource_type, action, ip_address, from/to, failures_only
    Summary permissions – non-admin → 403
    Summary aggregation – totals, failure counts, error_rate_pct, avg_response_ms,
                          by_action, by_role, by_resource (blank excluded),
                          by_status_class (values verified), zero-total edge case,
                          filters are forwarded to the summary queryset
    Serializer shape    – all expected fields are present in a detail response
    """

    def setUp(self):
        self.admin_user = User.objects.create_user(
            email="admin@example.com", password="Password123", role="admin"
        )
        self.teacher_user = User.objects.create_user(
            email="teacher@example.com", password="Password123", role="teacher"
        )

        self.log_view = AuditLog.objects.create(
            user=self.teacher_user,
            user_email=self.teacher_user.email,
            user_role="teacher",
            method="GET",
            path="/api/students/",
            response_status=200,
            action="read",
            resource_type="students",
            resource_id="42",
            ip_address="10.0.0.1",
            response_time_ms=120,
        )
        self.log_login_fail = AuditLog.objects.create(
            user=None,
            user_email="",
            user_role="anonymous",
            method="POST",
            path="/api/auth/login/",
            response_status=401,
            action="login.failed",
            ip_address="10.0.0.2",
            response_time_ms=40,
        )

        self.list_url    = reverse("audit-logs-list")
        self.summary_url = reverse("audit-logs-summary")

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _str_id(self, obj):
        """UUID primary keys are serialised as strings by DRF."""
        return str(obj.id)

    # ================================================================== #
    # Authentication
    # ================================================================== #

    def test_unauthenticated_user_cannot_list(self):
        """Anonymous requests should be rejected before any queryset/permission logic runs."""
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_unauthenticated_user_cannot_access_summary(self):
        response = self.client.get(self.summary_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    # ================================================================== #
    # List permissions
    # ================================================================== #

    def test_non_admin_sees_empty_list(self):
        """Non-admins receive an empty paginated result, not a 403."""
        self.client.force_authenticate(user=self.teacher_user)
        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 0)

    def test_admin_sees_all_logs(self):
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 2)

    # ================================================================== #
    # Retrieve permissions
    # ================================================================== #

    def test_non_admin_cannot_retrieve_log_entry(self):
        """Empty queryset for non-admins means any detail lookup returns 404."""
        self.client.force_authenticate(user=self.teacher_user)
        url = reverse("audit-logs-detail", args=[self.log_view.id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_admin_can_retrieve_log_entry(self):
        self.client.force_authenticate(user=self.admin_user)
        url = reverse("audit-logs-detail", args=[self.log_view.id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # UUID primary keys are returned as strings by DRF
        self.assertEqual(response.data["id"], self._str_id(self.log_view))

    # ================================================================== #
    # Read-only contract
    # ================================================================== #

    def test_post_to_list_is_not_allowed(self):
        """AuditLogViewSet is ReadOnlyModelViewSet — writes must be rejected."""
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.post(self.list_url, data={}, format="json")
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_patch_to_detail_is_not_allowed(self):
        self.client.force_authenticate(user=self.admin_user)
        url = reverse("audit-logs-detail", args=[self.log_view.id])
        response = self.client.patch(url, data={}, format="json")
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_delete_to_detail_is_not_allowed(self):
        self.client.force_authenticate(user=self.admin_user)
        url = reverse("audit-logs-detail", args=[self.log_view.id])
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    # ================================================================== #
    # Filtering — list endpoint
    # ================================================================== #

    def test_filter_by_response_status(self):
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(self.list_url, {"response_status": 401})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["id"], self._str_id(self.log_login_fail))

    def test_filter_by_method_case_insensitive(self):
        """The view upper()-s the param, so lowercase input must still match."""
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(self.list_url, {"method": "get"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["id"], self._str_id(self.log_view))

    def test_filter_failures_only(self):
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(self.list_url, {"failures_only": "true"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data["results"]
        self.assertEqual(len(results), 1)
        self.assertGreaterEqual(results[0]["response_status"], 400)

    def test_filter_by_user_role(self):
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(self.list_url, {"user_role": "anonymous"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["id"], self._str_id(self.log_login_fail))

    def test_filter_by_user_email(self):
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(self.list_url, {"user_email": "teacher@"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["id"], self._str_id(self.log_view))

    def test_filter_by_resource_type(self):
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(self.list_url, {"resource_type": "students"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["id"], self._str_id(self.log_view))

    def test_filter_by_action(self):
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(self.list_url, {"action": "login.failed"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["id"], self._str_id(self.log_login_fail))

    def test_filter_by_ip_address(self):
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(self.list_url, {"ip_address": "10.0.0.1"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["id"], self._str_id(self.log_view))

    def test_filter_from_excludes_older_entries(self):
        """'from' is inclusive; a timestamp after both logs should return nothing."""
        self.client.force_authenticate(user=self.admin_user)
        future = (timezone.now() + timezone.timedelta(hours=1)).isoformat()
        response = self.client.get(self.list_url, {"from": future})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 0)

    def test_filter_to_excludes_newer_entries(self):
        """'to' is inclusive; a timestamp before both logs should return nothing."""
        self.client.force_authenticate(user=self.admin_user)
        past = (timezone.now() - timezone.timedelta(hours=1)).isoformat()
        response = self.client.get(self.list_url, {"to": past})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 0)

    def test_failures_only_false_returns_all(self):
        """failures_only=false (or absent) must not restrict the queryset."""
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(self.list_url, {"failures_only": "false"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 2)

    # ================================================================== #
    # Serializer shape
    # ================================================================== #

    EXPECTED_FIELDS = {
        "id", "timestamp",
        "user", "user_email", "user_role", "ip_address", "user_agent",
        "method", "path", "query_params", "request_body",
        "response_status", "response_time_ms", "error_detail",
        "resource_type", "resource_id", "action", "action_display",
    }

    def test_detail_response_contains_all_expected_fields(self):
        self.client.force_authenticate(user=self.admin_user)
        url = reverse("audit-logs-detail", args=[self.log_view.id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(set(response.data.keys()), self.EXPECTED_FIELDS)

    def test_action_display_is_human_readable(self):
        """action_display should return the label from ACTION_CHOICES, not the code."""
        self.client.force_authenticate(user=self.admin_user)
        url = reverse("audit-logs-detail", args=[self.log_view.id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # "read" maps to "Read"
        self.assertEqual(response.data["action_display"], "Read")

    # ================================================================== #
    # Summary — permissions
    # ================================================================== #

    def test_non_admin_cannot_access_summary(self):
        """summary() has its own is_admin guard and must return 403, not 200."""
        self.client.force_authenticate(user=self.teacher_user)
        response = self.client.get(self.summary_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    # ================================================================== #
    # Summary — aggregation
    # ================================================================== #

    def test_summary_totals_and_error_rate(self):
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(self.summary_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total_requests"], 2)
        self.assertEqual(response.data["failed_requests"], 1)
        self.assertEqual(response.data["error_rate_pct"], 50.0)

    def test_summary_avg_response_time(self):
        """avg_response_ms should be the mean of response_time_ms across all rows."""
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(self.summary_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["avg_response_ms"], 80.0)  # (120 + 40) / 2

    def test_summary_by_action(self):
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(self.summary_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["by_action"]["read"], 1)
        self.assertEqual(response.data["by_action"]["login.failed"], 1)

    def test_summary_by_role(self):
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(self.summary_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["by_role"]["teacher"], 1)
        self.assertEqual(response.data["by_role"]["anonymous"], 1)

    def test_summary_by_resource_excludes_blank(self):
        """Entries with an empty resource_type must not appear in by_resource."""
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(self.summary_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["by_resource"], {"students": 1})

    def test_summary_by_status_class_keys_and_values(self):
        """Both 2xx and 4xx buckets should be present with the correct counts."""
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(self.summary_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        by_cls = response.data["by_status_class"]
        self.assertEqual(by_cls.get("2xx"), 1)
        self.assertEqual(by_cls.get("4xx"), 1)

    def test_summary_respects_filters(self):
        """summary() reuses get_queryset(), so query params must scope the aggregation."""
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(self.summary_url, {"failures_only": "true"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total_requests"], 1)
        self.assertEqual(response.data["failed_requests"], 1)
        self.assertEqual(response.data["error_rate_pct"], 100.0)

    def test_summary_zero_total_returns_zero_error_rate(self):
        """When no rows match the filter, error_rate_pct must be 0, not a ZeroDivisionError."""
        self.client.force_authenticate(user=self.admin_user)
        # Filter for a role that has no matching logs
        response = self.client.get(self.summary_url, {"user_role": "nonexistent"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total_requests"], 0)
        self.assertEqual(response.data["error_rate_pct"], 0)