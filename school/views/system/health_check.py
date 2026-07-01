from django.db import connection
from django.db.utils import OperationalError
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers as drf_serializers


@extend_schema(tags=["System"])
class HealthCheckView(APIView):
    permission_classes = [AllowAny]
    # Health checks are polled frequently by load balancers / uptime monitors
    # and must never be rate-limited. Just as importantly, DRF's throttle
    # classes read/write the SAME default cache this view probes, so leaving
    # throttling enabled here means anything that touches the cache (mocks
    # in tests, cache outages in prod) trips throttling machinery before our
    # own view code even runs. Disable it explicitly.
    throttle_classes = []

    @extend_schema(
        summary="System Health Check",
        responses={
            200: inline_serializer(
                name="HealthCheckSuccess",
                fields={
                    "status":    drf_serializers.CharField(default="healthy"),
                    "checks":    drf_serializers.DictField(child=drf_serializers.CharField()),
                    "timestamp": drf_serializers.DateTimeField(),
                }
            ),
            503: inline_serializer(
                name="HealthCheckFail",
                fields={
                    "status":    drf_serializers.CharField(default="degraded"),
                    "checks":    drf_serializers.DictField(child=drf_serializers.CharField()),
                    "timestamp": drf_serializers.DateTimeField(),
                }
            ),
        }
    )
    def get(self, request):
        checks  = {}
        overall = "healthy"

        try:
            connection.ensure_connection()
            with connection.cursor() as cur:
                cur.execute("SELECT 1")
            checks["database"] = "ok"
        except OperationalError as exc:
            checks["database"] = f"error: {exc}"
            overall = "degraded"

        try:
            from django.core.cache import cache
            _PROBE_KEY = "_health_check_probe"
            cache.set(_PROBE_KEY, "pong", timeout=5)
            val = cache.get(_PROBE_KEY)
            checks["cache"] = "ok" if val == "pong" else "error: read-back mismatch"
            if checks["cache"] != "ok":
                overall = "degraded"
        except Exception as exc:
            checks["cache"] = f"error: {exc}"
            overall = "degraded"

        http_status = (
            status.HTTP_200_OK
            if overall == "healthy"
            else status.HTTP_503_SERVICE_UNAVAILABLE
        )

        return Response(
            {"status": overall, "checks": checks, "timestamp": timezone.now()},
            status=http_status,
        )