from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from drf_spectacular.types import OpenApiTypes
from ..models import Announcement, Inquiry


class AnnouncementSerializer(serializers.ModelSerializer):
    author_name = serializers.SerializerMethodField()

    class Meta:
        model  = Announcement
        fields = "__all__"
        read_only_fields = ["author","created_at"]

    @extend_schema_field(OpenApiTypes.STR)
    def get_author_name(self, obj):
        return obj.author.full_name if obj.author else "School"


class InquirySerializer(serializers.ModelSerializer):
    class Meta:
        model = Inquiry
        fields = ['id', 'parent_name', 'email', 'phone', 'interested_class', 'created_at']
        read_only_fields = ['id', 'created_at']