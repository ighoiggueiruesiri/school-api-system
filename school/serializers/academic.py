from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from drf_spectacular.types import OpenApiTypes
from ..models import ClassRoom, Term, Student, Attendance, Assignment, DevelopmentReport


class ClassRoomSerializer(serializers.ModelSerializer):
    teacher_name      = serializers.SerializerMethodField()
    student_count     = serializers.SerializerMethodField()

    class Meta:
        model  = ClassRoom
        fields = "__all__"

    @extend_schema_field(OpenApiTypes.STR)
    def get_teacher_name(self, obj):
        return obj.teacher.full_name if obj.teacher else None

    @extend_schema_field(OpenApiTypes.INT)
    def get_student_count(self, obj):
        annotated = getattr(obj, "student_count_annotated", None)
        if annotated is not None:
            return annotated
        return obj.students.filter(is_active=True).count()


class TermSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Term
        fields = "__all__"


class StudentSerializer(serializers.ModelSerializer):
    full_name          = serializers.CharField(read_only=True)
    current_class_name = serializers.SerializerMethodField()
    age               = serializers.SerializerMethodField()

    class Meta:
        model  = Student
        fields = "__all__"
        read_only_fields = ["id","admission_number","created_at"]

    @extend_schema_field(OpenApiTypes.STR)
    def get_current_class_name(self, obj):
        return obj.current_class.name if obj.current_class else None

    @extend_schema_field(OpenApiTypes.INT)
    def get_age(self, obj):
        from django.utils import timezone
        today = timezone.now().date()
        dob   = obj.date_of_birth
        return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


class AttendanceSerializer(serializers.ModelSerializer):
    student_name     = serializers.SerializerMethodField()
    recorded_by_name = serializers.SerializerMethodField()

    class Meta:
        model  = Attendance
        fields = [
            "id", "date", "status", "reason", "outlook", "created_at",
            "student", "student_name", "term",
            "recorded_by", "recorded_by_name"
        ]
        read_only_fields = ["recorded_by","created_at"]

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
        help_text="List of {student_id, status, reason?} objects."
    )


class AssignmentSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Assignment
        fields = "__all__"
        read_only_fields = ["teacher","created_at"]


class DevelopmentReportSerializer(serializers.ModelSerializer):
    student_name    = serializers.SerializerMethodField()
    written_by_name = serializers.SerializerMethodField()

    class Meta:
        model  = DevelopmentReport
        fields = "__all__"
        read_only_fields = ["written_by","created_at"]

    @extend_schema_field(OpenApiTypes.STR)
    def get_student_name(self, obj):    
        return obj.student.full_name

    @extend_schema_field(OpenApiTypes.STR)
    def get_written_by_name(self, obj): 
        return obj.written_by.full_name if obj.written_by else None