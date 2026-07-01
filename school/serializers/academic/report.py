from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from drf_spectacular.types import OpenApiTypes

from ...models import AcademicReport, SubjectScore


class SubjectScoreSerializer(serializers.ModelSerializer):
    """
    A single subject row inside an elementary report.
    `total_score` and `grade` are computed properties on the model — read-only here.
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


class AcademicReportSerializer(serializers.ModelSerializer):
    """
    Full academic report.

    - `subject_scores` nested field is used only when report_type == 'elementary'.
    - Preschool section fields are used only when report_type == 'preschool'.
    - Nested subject scores are fully replaced on every update.
    """
    student_name    = serializers.SerializerMethodField()
    written_by_name = serializers.SerializerMethodField()
    term_display    = serializers.SerializerMethodField()
    subject_scores  = SubjectScoreSerializer(many=True, required=False, default=list)

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
        report      = AcademicReport.objects.create(**validated_data)
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


class AcademicReportListSerializer(serializers.ModelSerializer):
    """
    Lightweight serializer for the reports table (list view).
    Avoids sending every preschool/elementary field on paginated responses.
    """
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
