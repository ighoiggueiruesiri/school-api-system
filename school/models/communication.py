import uuid
from django.db import models
from django.contrib.postgres.indexes import GinIndex


class Announcement(models.Model):
    """School notice sent to parents or teachers."""
    AUDIENCE = [
        ("all",      "Everyone"),
        ("parents",  "All Parents"),
        ("teachers", "All Teachers"),
    ]
    title      = models.CharField(max_length=200)
    body       = models.TextField()
    audience   = models.CharField(max_length=10, choices=AUDIENCE, default="all")
    author     = models.ForeignKey("school.User", on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "announcements"
        ordering = ["-created_at"]
        indexes = [
            GinIndex(
                name='announce_search_idx',
                fields=['title', 'body'],
                opclasses=['gin_trgm_ops', 'gin_trgm_ops']
            )
        ]

    def __str__(self):
        return self.title


class Inquiry(models.Model):
    """Lead capture from the frontend pop-up."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    parent_name = models.CharField(max_length=150)
    email = models.EmailField()
    phone = models.CharField(max_length=20)
    interested_class = models.CharField(max_length=50, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "inquiries"
        ordering = ["-created_at"]
        indexes = [
            GinIndex(
                name='inquiry_search_idx',
                fields=['parent_name', 'email', 'phone'],
                opclasses=['gin_trgm_ops', 'gin_trgm_ops', 'gin_trgm_ops']
            )
        ]

    def __str__(self):
        return f"{self.parent_name} - {self.phone}"