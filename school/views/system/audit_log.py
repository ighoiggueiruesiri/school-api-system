from django.db.models import Count, Q, Avg
from rest_framework import viewsets, filters
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter, OpenApiTypes, inline_serializer
from rest_framework import serializers as drf_serializers

from ...models import AuditLog
from ...serializers import AuditLogSerializer
from ..base import DynamicPageSizePagination, is_admin


@extend_schema(tags=["System Audit"])
@extend_schema_view(
    list=extend_schema(
        summary="List audit log entries (Admin only)",
        parameters=[
            OpenApiParameter(name="user_email",      description="Filter by actor email",                       required=False, type=OpenApiTypes.STR),
            OpenApiParameter(name="user_role",       description="Filter by role: admin|editor|teacher|parent", required=False, type=OpenApiTypes.STR),
            OpenApiParameter(name="method",          description="HTTP verb: GET|POST|PATCH|DELETE",            required=False, type=OpenApiTypes.STR),
            OpenApiParameter(name="response_status", description="HTTP status code, e.g. 200 or 403",          required=False, type=OpenApiTypes.INT),
            OpenApiParameter(name="resource_type",   description="Resource name, e.g. students|invoices",      required=False, type=OpenApiTypes.STR),
            OpenApiParameter(name="action",          description="Action code, e.g. login.success|delete",     required=False, type=OpenApiTypes.STR),
            OpenApiParameter(name="ip_address",      description="Filter by client IP address",                required=False, type=OpenApiTypes.STR),
            OpenApiParameter(name="from",            description="ISO date-time: 2025-01-01T00:00:00",         required=False, type=OpenApiTypes.DATETIME),
            OpenApiParameter(name="to",              description="ISO date-time: 2025-12-31T23:59:59",         required=False, type=OpenApiTypes.DATETIME),
            OpenApiParameter(name="failures_only",   description="true — show only 4xx / 5xx responses",       required=False, type=OpenApiTypes.BOOL),
            OpenApiParameter(name="page_size",       description="Results per page (default 25)",              required=False, type=OpenApiTypes.INT),
        ]
    ),
    retrieve=extend_schema(summary="Retrieve a single audit log entry (Admin only)"),
)
class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset           = AuditLog.objects.none()
    serializer_class   = AuditLogSerializer
    permission_classes = [IsAuthenticated]
    pagination_class   = DynamicPageSizePagination
    filter_backends    = [filters.SearchFilter]
    search_fields      = ["user_email", "path", "ip_address"]

    def get_queryset(self):
        if not is_admin(self.request.user):
            return AuditLog.objects.none()

        qs = AuditLog.objects.select_related("user")
        p  = self.request.query_params

        if p.get("user_email"):      qs = qs.filter(user_email__icontains=p["user_email"])
        if p.get("user_role"):       qs = qs.filter(user_role=p["user_role"])
        if p.get("method"):          qs = qs.filter(method=p["method"].upper())
        if p.get("response_status"): qs = qs.filter(response_status=p["response_status"])
        if p.get("resource_type"):   qs = qs.filter(resource_type=p["resource_type"])
        if p.get("action"):          qs = qs.filter(action=p["action"])
        if p.get("ip_address"):      qs = qs.filter(ip_address=p["ip_address"])
        if p.get("from"):            qs = qs.filter(timestamp__gte=p["from"])
        if p.get("to"):              qs = qs.filter(timestamp__lte=p["to"])
        if p.get("failures_only", "").lower() == "true":
            qs = qs.filter(response_status__gte=400)

        return qs.order_by("-timestamp")

    @extend_schema(
        summary="Aggregated counts for the audit dashboard (Admin only)",
        responses={200: inline_serializer(
            name="AuditSummaryResponse",
            fields={
                "total_requests":  drf_serializers.IntegerField(),
                "failed_requests": drf_serializers.IntegerField(),
                "error_rate_pct":  drf_serializers.FloatField(),
                "avg_response_ms": drf_serializers.FloatField(),
                "by_action":       drf_serializers.DictField(child=drf_serializers.IntegerField()),
                "by_resource":     drf_serializers.DictField(child=drf_serializers.IntegerField()),
                "by_status_class": drf_serializers.DictField(child=drf_serializers.IntegerField()),
                "by_role":         drf_serializers.DictField(child=drf_serializers.IntegerField()),
            }
        )}
    )
    @action(detail=False, methods=["get"])
    def summary(self, request):
        if not is_admin(request.user):
            return Response({"error": "Admin access required."}, status=403)

        qs  = self.get_queryset()
        agg = qs.aggregate(
            total=Count("id"),
            failed=Count("id", filter=Q(response_status__gte=400)),
            avg_resp=Avg("response_time_ms"),
        )
        total    = agg["total"]
        failed   = agg["failed"]
        avg_resp = agg["avg_resp"] or 0

        by_action = {
            row["action"]: row["cnt"]
            for row in qs.values("action").annotate(cnt=Count("id"))
        }
        by_resource = {
            row["resource_type"]: row["cnt"]
            for row in qs.exclude(resource_type="")
                         .values("resource_type")
                         .annotate(cnt=Count("id"))
                         .order_by("-cnt")[:10]
        }
        by_status_class = {}
        for row in qs.values("response_status").annotate(cnt=Count("id")):
            cls = f"{row['response_status'] // 100}xx"
            by_status_class[cls] = by_status_class.get(cls, 0) + row["cnt"]

        by_role = {
            row["user_role"] or "anonymous": row["cnt"]
            for row in qs.values("user_role").annotate(cnt=Count("id"))
        }

        return Response({
            "total_requests":  total,
            "failed_requests": failed,
            "error_rate_pct":  round(failed / total * 100, 2) if total else 0,
            "avg_response_ms": round(avg_resp, 1),
            "by_action":       by_action,
            "by_resource":     by_resource,
            "by_status_class": by_status_class,
            "by_role":         by_role,
        })
