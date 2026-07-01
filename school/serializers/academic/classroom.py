from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from drf_spectacular.types import OpenApiTypes

from ...models import ClassRoom


class ClassRoomSerializer(serializers.ModelSerializer):
    teacher_name  = serializers.SerializerMethodField()
    student_count = serializers.SerializerMethodField()

    class Meta:
        model  = ClassRoom
        fields = "__all__"

    @extend_schema_field(OpenApiTypes.STR)
    def get_teacher_name(self, obj):
        return obj.teacher.full_name if obj.teacher else None

    @extend_schema_field(OpenApiTypes.INT)
    def get_student_count(self, obj):
        # Prefer the annotated value from the queryset (avoids an extra query)
        annotated = getattr(obj, "student_count_annotated", None)
        if annotated is not None:
            return annotated
        return obj.students.filter(is_active=True).count()
