from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from drf_spectacular.types import OpenApiTypes

from ...models import Expenditure


class ExpenditureSerializer(serializers.ModelSerializer):
    """School outgoing — salary, utilities, supplies, maintenance, etc."""
    recorded_by_name = serializers.SerializerMethodField()
    category_display = serializers.SerializerMethodField()

    class Meta:
        model  = Expenditure
        fields = [
            "id",
            "date",
            "category",
            "category_display",
            "description",
            "amount",
            "reference",
            "notes",
            "recorded_by",
            "recorded_by_name",
            "created_at",
        ]
        read_only_fields = ["id", "recorded_by", "created_at"]

    @extend_schema_field(OpenApiTypes.STR)
    def get_recorded_by_name(self, obj):
        return obj.recorded_by.full_name if obj.recorded_by else None

    @extend_schema_field(OpenApiTypes.STR)
    def get_category_display(self, obj):
        return obj.get_category_display()
