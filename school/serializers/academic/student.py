from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from drf_spectacular.types import OpenApiTypes

from ...models import Student


class StudentSerializer(serializers.ModelSerializer):
    full_name          = serializers.CharField(read_only=True)
    current_class_name = serializers.SerializerMethodField()
    age                = serializers.SerializerMethodField()

    class Meta:
        model            = Student
        fields           = "__all__"
        read_only_fields = ["id", "admission_number", "created_at"]

    @extend_schema_field(OpenApiTypes.STR)
    def get_current_class_name(self, obj):
        return obj.current_class.name if obj.current_class else None

    @extend_schema_field(OpenApiTypes.INT)
    def get_age(self, obj):
        from django.utils import timezone
        today = timezone.now().date()
        dob   = obj.date_of_birth
        return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
