from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from drf_spectacular.types import OpenApiTypes
from ..models import (
    ClassRoom, Term, Student, Attendance, Assignment,
    AcademicReport, SubjectScore,
    ELEMENTARY_SUBJECTS,
)


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

'''
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
'''

class SubjectScoreSerializer(serializers.ModelSerializer):
    """
    Serializer for a single subject row inside an elementary report.
    `total_score` and `grade` are computed read-only fields.
    """
    total_score = serializers.SerializerMethodField()
    grade       = serializers.SerializerMethodField()

    class Meta:
        model  = SubjectScore
        fields = [
            "id",
            "subject",
            "cat_score",
            "exam_score",
            "total_score",
            "grade",
            "wh_behaviour",
            "wh_listens",
            "wh_completes_work",
            "wh_contributes",
            "wh_homework",
        ]
        read_only_fields = ["id", "total_score", "grade"]

    @extend_schema_field(OpenApiTypes.INT)
    def get_total_score(self, obj):
        return obj.total_score

    @extend_schema_field(OpenApiTypes.STR)
    def get_grade(self, obj):
        return obj.grade


# ---------------------------------------------------------------------------
# AcademicReport serializer  (replaces DevelopmentReportSerializer)
# ---------------------------------------------------------------------------

class AcademicReportSerializer(serializers.ModelSerializer):
    """
    Full academic report.  The `subject_scores` nested field is used only
    when `report_type == 'elementary'`; preschool section fields are used
    only when `report_type == 'preschool'`.

    Nested subject scores are created / replaced in full on every write.
    """
    student_name    = serializers.SerializerMethodField()
    written_by_name = serializers.SerializerMethodField()
    term_display    = serializers.SerializerMethodField()

    # Nested list of subject scores (elementary only)
    subject_scores = SubjectScoreSerializer(many=True, required=False, default=list)

    class Meta:
        model  = AcademicReport
        fields = [
            # identifiers
            "id", "student", "student_name", "term", "term_display",
            "written_by", "written_by_name",
            "report_type",

            # elementary — attendance
            "attendance_present", "attendance_total",

            # elementary — psychomotor domains
            "pm_fluent_reading", "pm_elocution", "pm_handwriting",
            "pm_sports_games", "pm_creativity",

            # elementary — subject scores (nested)
            "subject_scores",

            # preschool — literacy
            "lit_speaks_clearly", "lit_letter_sounds", "lit_phonics",
            "lit_local_pets", "lit_picture_story", "lit_comment",

            # preschool — socio-emotional
            "se_follows_routines", "se_manages_emotions", "se_says_name_age",
            "se_magic_words", "se_identifies_objects", "se_comment",

            # preschool — numeracy
            "num_count_write_20", "num_shapes_colors", "num_many_few",
            "num_match_objects", "num_count_40", "num_comment",

            # preschool — science
            "sci_sense_organs", "sci_plants", "sci_animals",
            "sci_body_parts", "sci_weather", "sci_comment",

            # preschool — practical life
            "pl_pencil_crayon", "pl_wash_hands", "pl_take_turns",
            "pl_pour_liquid", "pl_zip_button", "pl_table_manners", "pl_comment",

            # common
            "teacher_comment", "head_teacher_comment",
            "is_published", "created_at",
        ]
        read_only_fields = ["id", "written_by", "created_at"]

    # ------------------------------------------------------------------
    # Computed display fields
    # ------------------------------------------------------------------

    @extend_schema_field(OpenApiTypes.STR)
    def get_student_name(self, obj):
        return obj.student.full_name

    @extend_schema_field(OpenApiTypes.STR)
    def get_written_by_name(self, obj):
        return obj.written_by.full_name if obj.written_by else None

    @extend_schema_field(OpenApiTypes.STR)
    def get_term_display(self, obj):
        return str(obj.term)

    # ------------------------------------------------------------------
    # Nested write: create
    # ------------------------------------------------------------------

    def create(self, validated_data):
        scores_data = validated_data.pop("subject_scores", [])
        report = AcademicReport.objects.create(**validated_data)
        self._save_scores(report, scores_data)
        return report

    # ------------------------------------------------------------------
    # Nested write: update  (scores are fully replaced on each update)
    # ------------------------------------------------------------------

    def update(self, instance, validated_data):
        scores_data = validated_data.pop("subject_scores", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if scores_data is not None:
            instance.subject_scores.all().delete()
            self._save_scores(instance, scores_data)
        return instance

    # ------------------------------------------------------------------
    # Helper
    # ------------------------------------------------------------------

    @staticmethod
    def _save_scores(report, scores_data):
        SubjectScore.objects.bulk_create([
            SubjectScore(report=report, **score)
            for score in scores_data
        ])


# ---------------------------------------------------------------------------
# Lightweight list serializer (avoids sending every field on the list view)
# ---------------------------------------------------------------------------

class AcademicReportListSerializer(serializers.ModelSerializer):
    """Minimal fields for the reports table — used in list endpoints."""
    student_name    = serializers.SerializerMethodField()
    written_by_name = serializers.SerializerMethodField()
    term_display    = serializers.SerializerMethodField()

    class Meta:
        model  = AcademicReport
        fields = [
            "id", "student", "student_name",
            "term", "term_display",
            "report_type",
            "written_by", "written_by_name",
            "is_published", "created_at",
        ]

    @extend_schema_field(OpenApiTypes.STR)
    def get_student_name(self, obj):
        return obj.student.full_name

    @extend_schema_field(OpenApiTypes.STR)
    def get_written_by_name(self, obj):
        return obj.written_by.full_name if obj.written_by else None

    @extend_schema_field(OpenApiTypes.STR)
    def get_term_display(self, obj):
        return str(obj.term)