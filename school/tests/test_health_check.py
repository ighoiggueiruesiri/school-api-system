from unittest.mock import patch, MagicMock
from django.db.utils import OperationalError
from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APITestCase
from rest_framework import status
from django.urls import reverse


# Pin the cache backend used by these tests to an in-memory cache. The health
# check probes django.core.cache.cache directly, so if the project's
# configured backend (e.g. django-redis) points at a Redis instance that
# isn't running wherever the tests execute, the "healthy" test will fail for
# infrastructure reasons that have nothing to do with the view's logic.
TEST_CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "health-check-tests",
    }
}


@override_settings(CACHES=TEST_CACHES)
class HealthCheckViewTests(APITestCase):
    def setUp(self):
        self.health_url = reverse("health")
        cache.clear()

    # ------------------------------------------------------------------
    # Happy path
    # ------------------------------------------------------------------

    def test_health_check_healthy(self):
        """Fully operational system returns 200 with all checks passing."""
        response = self.client.get(self.health_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "healthy")
        self.assertEqual(response.data["checks"]["database"], "ok")
        self.assertEqual(response.data["checks"]["cache"], "ok")
        self.assertIn("timestamp", response.data)

    # ------------------------------------------------------------------
    # Database failure
    # ------------------------------------------------------------------

    @patch("django.db.connection.ensure_connection")
    def test_health_check_db_failure(self, mock_ensure):
        """A database OperationalError on ensure_connection degrades status to 503."""
        mock_ensure.side_effect = OperationalError("Connection refused")

        response = self.client.get(self.health_url)

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(response.data["status"], "degraded")
        self.assertIn("error: Connection refused", response.data["checks"]["database"])

    # ------------------------------------------------------------------
    # Cache failures
    # ------------------------------------------------------------------

    @patch.object(cache, "set", side_effect=Exception("Redis timeout"))
    def test_health_check_cache_set_failure(self, _mock_set):
        """An exception raised by cache.set degrades status to 503."""
        response = self.client.get(self.health_url)

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(response.data["status"], "degraded")
        self.assertIn("error: Redis timeout", response.data["checks"]["cache"])

    @patch.object(cache, "get", return_value="wrong_value")
    @patch.object(cache, "set")
    def test_health_check_cache_readback_mismatch(self, _mock_set, _mock_get):
        """A cache read-back mismatch (set succeeds but get returns wrong value)
        degrades status to 503."""
        response = self.client.get(self.health_url)

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(response.data["status"], "degraded")
        self.assertEqual(
            response.data["checks"]["cache"], "error: read-back mismatch"
        )

    # ------------------------------------------------------------------
    # Simultaneous failures
    # ------------------------------------------------------------------

    @patch("django.db.connection.ensure_connection")
    @patch.object(cache, "set", side_effect=Exception("Redis timeout"))
    def test_health_check_db_and_cache_failure(self, _mock_set, mock_ensure):
        """Both subsystems failing returns 503 with both checks marked as errors."""
        mock_ensure.side_effect = OperationalError("DB down")

        response = self.client.get(self.health_url)

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(response.data["status"], "degraded")
        self.assertIn("error:", response.data["checks"]["database"])
        self.assertIn("error:", response.data["checks"]["cache"])