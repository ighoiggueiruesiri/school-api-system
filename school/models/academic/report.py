from django.db import models
from django.contrib.postgres.indexes import GinIndex

from .student   import Student
from .term      import Term
from .constants import WORK_HABIT_CHOICES, ELEMENTARY_SUBJECTS


class AcademicReport(models.Model):
    """
    Term report for a student. Supports two layouts:
      - 'elementary': subject scores + work habits + psychomotor domains
      - 'preschool' : sectional skill assessments (Literacy, Socio-emotional,
                      Numeracy, Science, Practical Life)
    """
    REPORT_TYPES = [("elementary", "Elementary"), ("preschool", "Preschool")]

    student     = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="academic_reports")
    term        = models.ForeignKey(Term, on_delete=models.CASCADE)
    written_by  = models.ForeignKey("school.User", on_delete=models.SET_NULL, null=True)
    report_type = models.CharField(max_length=15, choices=REPORT_TYPES)

    # ------------------------------------------------------------------
    # Elementary — attendance
    # ------------------------------------------------------------------
    attendance_present = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text="Days the child was present this term",
    )
    attendance_total = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text="Total school days this term",
    )

    # ------------------------------------------------------------------
    # Elementary — psychomotor domains (scale 1–5)
    # ------------------------------------------------------------------
    pm_fluent_reading = models.PositiveSmallIntegerField(null=True, blank=True)
    pm_elocution      = models.PositiveSmallIntegerField(null=True, blank=True)
    pm_handwriting    = models.PositiveSmallIntegerField(null=True, blank=True)
    pm_sports_games   = models.PositiveSmallIntegerField(null=True, blank=True)
    pm_creativity     = models.PositiveSmallIntegerField(null=True, blank=True)

    # ------------------------------------------------------------------
    # Preschool — Literacy section (scale 1–5 per skill)
    # ------------------------------------------------------------------
    lit_speaks_clearly = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text="Speaks clearly and uses appropriate language",
    )
    lit_letter_sounds = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text="Can sound and say letter sounds a–j and match to objects",
    )
    lit_phonics = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text="Can identify and trace the sounds s, a, t, p, i, n",
    )
    lit_local_pets = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text="Can identify and mention local pets",
    )
    lit_picture_story = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text="Can arrange a 3-picture story in correct chronological order",
    )
    lit_comment = models.TextField(blank=True)

    # ------------------------------------------------------------------
    # Preschool — Socio-emotional Skills (scale 1–5)
    # ------------------------------------------------------------------
    se_follows_routines = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text="Follows routines, asks questions and responds to questions",
    )
    se_manages_emotions = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text="Shows and manages emotions (anger, hunger, happiness)",
    )
    se_says_name_age = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text="Can say name and age, follows directions and shares with others",
    )
    se_magic_words = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text="Can say their five magic words and uses them when needed",
    )
    se_identifies_objects = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text="Can identify and feel objects around them",
    )
    se_comment = models.TextField(blank=True)

    # ------------------------------------------------------------------
    # Preschool — Numeracy (scale 1–5)
    # ------------------------------------------------------------------
    num_count_write_20 = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text="Can count, identify, trace and write numbers 1–20",
    )
    num_shapes_colors = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text="Can identify shapes (circle, triangle, square) and colours",
    )
    num_many_few = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text="Can identify many/few, big/small, full/empty",
    )
    num_match_objects = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text="Can match objects to their numbers from 1–10",
    )
    num_count_40 = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text="Can count and recite numbers 1–40",
    )
    num_comment = models.TextField(blank=True)

    # ------------------------------------------------------------------
    # Preschool — Science (scale 1–5)
    # ------------------------------------------------------------------
    sci_sense_organs = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text="Can identify the five sense organs and say what they do",
    )
    sci_plants = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text="Can say what plants are and identify them in the environment",
    )
    sci_animals = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text="Can identify and mention examples of animals in the locality",
    )
    sci_body_parts = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text="Can identify different body parts and match them to what they do",
    )
    sci_weather = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text="Can say what the weather is (rainy or sunny)",
    )
    sci_comment = models.TextField(blank=True)

    # ------------------------------------------------------------------
    # Preschool — Practical Life (scale 1–5)
    # ------------------------------------------------------------------
    pl_pencil_crayon = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text="Can hold and use a pencil, crayon or glue stick",
    )
    pl_wash_hands = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text="Can wash hands with minimal help",
    )
    pl_take_turns = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text="Can take turns, follow directions and share with others",
    )
    pl_pour_liquid = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text="Can pour liquid material with control",
    )
    pl_zip_button = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text="Can zip a jacket, buckle shoes, wash hands properly and button shirts",
    )
    pl_table_manners = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text="Practices good table manners and hygiene",
    )
    pl_comment = models.TextField(blank=True)

    # ------------------------------------------------------------------
    # Common fields
    # ------------------------------------------------------------------
    teacher_comment      = models.TextField()
    head_teacher_comment = models.TextField(blank=True)
    is_published         = models.BooleanField(default=False)
    created_at           = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table        = "academic_reports"
        unique_together = ["student", "term"]
        ordering        = ["-created_at"]
        indexes         = [
            GinIndex(
                name="academic_report_search_idx",
                fields=["teacher_comment", "head_teacher_comment"],
                opclasses=["gin_trgm_ops", "gin_trgm_ops"],
            )
        ]

    def __str__(self):
        return f"Report: {self.student.full_name} — {self.term}"


class SubjectScore(models.Model):
    """
    Scores and work-habit ratings for a single subject within an
    elementary AcademicReport. One row per subject per report.
    """
    report  = models.ForeignKey(
        AcademicReport, on_delete=models.CASCADE, related_name="subject_scores"
    )
    subject = models.CharField(max_length=20, choices=ELEMENTARY_SUBJECTS)

    # Raw scores
    cat_score  = models.PositiveSmallIntegerField(default=0, help_text="Continuous Assessment score")
    exam_score = models.PositiveSmallIntegerField(default=0, help_text="Examination score")

    # Work-habit ratings (one per habit per subject)
    wh_behaviour      = models.CharField(max_length=2, choices=WORK_HABIT_CHOICES, default="LS",
                                         help_text="Comports self with good behaviour during class work")
    wh_listens        = models.CharField(max_length=2, choices=WORK_HABIT_CHOICES, default="LS",
                                         help_text="Listens attentively and gives best effort")
    wh_completes_work = models.CharField(max_length=2, choices=WORK_HABIT_CHOICES, default="LS",
                                         help_text="Completes work on time")
    wh_contributes    = models.CharField(max_length=2, choices=WORK_HABIT_CHOICES, default="LS",
                                         help_text="Contributes to class discussions")
    wh_homework       = models.CharField(max_length=2, choices=WORK_HABIT_CHOICES, default="LS",
                                         help_text="Completes homework")

    class Meta:
        db_table        = "subject_scores"
        unique_together = ["report", "subject"]
        ordering        = ["report", "subject"]

    @property
    def total_score(self) -> int:
        return self.cat_score + self.exam_score

    @property
    def grade(self) -> str:
        t = self.total_score
        if t >= 95: return "A+"
        if t >= 90: return "A"
        if t >= 85: return "B+"
        if t >= 80: return "B"
        if t >= 75: return "C+"
        if t >= 70: return "C"
        if t >= 65: return "D+"
        if t >= 60: return "D"
        return "E"

    def __str__(self):
        return f"{self.get_subject_display()} — {self.report}"