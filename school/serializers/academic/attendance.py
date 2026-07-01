from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from drf_spectacular.types import OpenApiTypes

from ...models import Attendance, Term


class AttendanceSerializer(serializers.ModelSerializer):
    student_name     = serializers.SerializerMethodField()
    recorded_by_name = serializers.SerializerMethodField()

    class Meta:
        model  = Attendance
        fields = [
            "id", "date", "status", "reason", "outlook", "created_at",
            "student", "student_name", "term",
            "recorded_by", "recorded_by_name",
        ]
        read_only_fields = ["recorded_by", "created_at"]

    @extend_schema_field(OpenApiTypes.STR)
    def get_student_name(self, obj):
        return obj.student.full_name

    @extend_schema_field(OpenApiTypes.STR)
    def get_recorded_by_name(self, obj):
        return obj.recorded_by.full_name if obj.recorded_by else None


class BulkAttendanceSerializer(serializers.Serializer):
    """Mark attendance for a whole class in one API call."""
    date    = serializers.DateField()
    term    = serializers.PrimaryKeyRelatedField(queryset=Term.objects.all())
    records = serializers.ListField(
        child=serializers.DictField(),
        min_length=1,
        help_text="List of {student_id, status, reason?} objects.",
    )
