from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from drf_spectacular.types import OpenApiTypes

from ...models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    """
    Read-only serializer for AuditLog.
    Exposed only to admins via GET /api/audit-logs/.
    """
    action_display = serializers.SerializerMethodField()

    class Meta:
        model  = AuditLog
        fields = [
            "id", "timestamp",
            "user", "user_email", "user_role", "ip_address", "user_agent",
            "method", "path", "query_params", "request_body",
            "response_status", "response_time_ms", "error_detail",
            "resource_type", "resource_id", "action", "action_display",
        ]
        read_only_fields = fields

    @extend_schema_field(OpenApiTypes.STR)
    def get_action_display(self, obj):
        return obj.get_action_display()
