import uuid
from django.db import models


class AuditLog(models.Model):
    """
    Immutable record of every API action — who did what, when, and with what result.
    """
    ACTION_CHOICES = [
        ("login.success", "Login Success"),
        ("login.failed",  "Login Failed"),
        ("logout",        "Logout"),
        ("register",      "Register"),
        ("create",        "Create"),
        ("read",          "Read"),
        ("update",        "Update"),
        ("delete",        "Delete"),
        ("bulk",          "Bulk Operation"),
        ("action",        "Custom Action"),
        ("health_check",  "Health Check"),
        ("error",         "Server Error"),
    ]

    id               = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user             = models.ForeignKey(
        "school.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="audit_logs",
    )
    user_email       = models.EmailField(blank=True)
    user_role        = models.CharField(max_length=10, blank=True)
    ip_address       = models.GenericIPAddressField(null=True, blank=True)
    user_agent       = models.TextField(blank=True)
    method           = models.CharField(max_length=10)
    path             = models.CharField(max_length=500)
    query_params     = models.JSONField(default=dict, blank=True)
    request_body     = models.JSONField(default=dict, blank=True)
    response_status  = models.PositiveSmallIntegerField()
    response_time_ms = models.PositiveIntegerField(default=0)
    resource_type    = models.CharField(max_length=50, blank=True)
    resource_id      = models.CharField(max_length=100, blank=True)
    action           = models.CharField(max_length=20, choices=ACTION_CHOICES, default="read")
    error_detail     = models.TextField(blank=True)
    timestamp        = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "audit_logs"
        ordering = ["-timestamp"]
        indexes  = [
            models.Index(fields=["user",            "-timestamp"], name="audit_user_ts_idx"),
            models.Index(fields=["resource_type",   "-timestamp"], name="audit_resource_ts_idx"),
            models.Index(fields=["response_status", "-timestamp"], name="audit_status_ts_idx"),
            models.Index(fields=["action",          "-timestamp"], name="audit_action_ts_idx"),
            models.Index(fields=["ip_address",      "-timestamp"], name="audit_ip_ts_idx"),
        ]

    def __str__(self):
        actor = self.user_email or "anon"
        return f"[{self.timestamp:%Y-%m-%d %H:%M:%S}] {actor} {self.method} {self.path} → {self.response_status}"
