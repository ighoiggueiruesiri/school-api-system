import uuid
from django.db import models
from django.utils import timezone
from django.contrib.postgres.indexes import GinIndex
from ..storage import validate_file_size, compress_image

WORK_HABIT_CHOICES = [
    ("MS", "Mastered Skills"),
    ("LS", "Learning Skills"),
    ("AC", "Area of Concern"),
    ("NA", "Not Applicable"),
]

ELEMENTARY_SUBJECTS = [
    ("MATH",         "Math"),
    ("ENGLISH",      "English"),
    ("SOCIAL_STUDIES", "Social Studies"),
    ("SCIENCE",      "Science"),
    ("CRK",          "C.R.K"),
    ("PHSE",         "P.H.S.E"),
    ("CCA",          "CCA"),
    ("QUANT_RSN",    "Quant Reasoning"),
    ("VERBAL_RSN",   "Verbal Reasoning"),
    ("ICT",          "ICT"),
]

class ClassRoom(models.Model):
    """A class in the school, e.g. Nursery 1, Primary 2."""
    name    = models.CharField(max_length=50, unique=True)
    level   = models.PositiveSmallIntegerField()          # for ordering
    teacher = models.ForeignKey(
        "school.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="class_taught",
        limit_choices_to={"role": "teacher"},
    )
    capacity = models.PositiveSmallIntegerField(default=20)

    class Meta:
        db_table  = "classrooms"
        ordering  = ["level"]
        indexes = [
            GinIndex(
                name='classroom_search_idx',
                fields=['name'],
                opclasses=['gin_trgm_ops']
            )
        ]

    def __str__(self):
        return self.name


class Term(models.Model):
    """School term, e.g. First Term 2024/2025."""
    TERM_NAMES = [("first", "First Term"), ("second", "Second Term"), ("third", "Third Term")]
    name          = models.CharField(max_length=10, choices=TERM_NAMES)
    academic_year = models.CharField(max_length=10)    # "2024/2025"
    start_date    = models.DateField()
    end_date      = models.DateField()
    is_current    = models.BooleanField(default=False)

    class Meta:
        db_table        = "terms"
        unique_together = ["name", "academic_year"]

    def __str__(self):
        return f"{self.get_name_display()} {self.academic_year}"

    def save(self, *args, **kwargs):
        if self.is_current:
            Term.objects.exclude(pk=self.pk).update(is_current=False)
        super().save(*args, **kwargs)


class Student(models.Model):
    """A child enrolled at the school."""
    GENDER = [("male", "Male"), ("female", "Female")]

    id               = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    admission_number = models.CharField(max_length=20, unique=True)
    first_name       = models.CharField(max_length=100)
    last_name        = models.CharField(max_length=100)
    date_of_birth    = models.DateField()
    gender           = models.CharField(max_length=10, choices=GENDER)
    profile_photo    = models.ImageField(
        upload_to="students/", null=True, blank=True,
        validators=[validate_file_size]
    )
    current_class    = models.ForeignKey(ClassRoom, on_delete=models.SET_NULL, null=True, related_name="students")
    parents          = models.ManyToManyField("school.User", related_name="children", blank=True,
                                              limit_choices_to={"role": "parent"})
    admission_date   = models.DateField(default=timezone.now)
    is_active        = models.BooleanField(default=True)
    allergies        = models.TextField(blank=True)
    notes            = models.TextField(blank=True)
    created_at       = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "students"
        ordering = ["current_class__level", "last_name", "first_name"]
        indexes = [
            GinIndex(
                name='student_search_idx',
                fields=['first_name', 'last_name', 'admission_number'],
                opclasses=['gin_trgm_ops', 'gin_trgm_ops', 'gin_trgm_ops']
            )
        ]

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.admission_number})"

    def save(self, *args, **kwargs):
        if self.profile_photo and hasattr(self.profile_photo, 'file'):
            try:
                compressed = compress_image(
                    self.profile_photo, "student",
                    self.profile_photo.name or "student.jpg"
                )
                self.profile_photo.save("student.jpg", compressed, save=False)
            except Exception:
                pass
        super().save(*args, **kwargs)

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"


class Attendance(models.Model):
    STATUS = [
        ("present", "Present"),
        ("absent",  "Absent"),
        ("late",    "Late"),
        ("excused", "Excused"),
    ]
    student     = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="attendance")
    date        = models.DateField()
    status      = models.CharField(max_length=10, choices=STATUS)
    reason      = models.CharField(max_length=200, blank=True)
    outlook     = models.CharField(max_length=255, blank=True, help_text="Child's mood/outlook on arrival")
    recorded_by = models.ForeignKey("school.User", on_delete=models.SET_NULL, null=True)
    term        = models.ForeignKey(Term, on_delete=models.CASCADE)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table        = "attendance"
        unique_together = ["student", "date"]   # one record per student per day
        ordering        = ["-date"]
        indexes = [
            GinIndex(
                name='attendance_search_idx',
                fields=['reason', 'outlook'],
                opclasses=['gin_trgm_ops', 'gin_trgm_ops']
            )
        ]

    def __str__(self):
        return f"{self.student.full_name} — {self.date} — {self.status}"


class Assignment(models.Model):
    """Homework or classwork."""
    TYPE = [("homework", "Homework"), ("classwork", "Classwork"), ("project", "Project")]

    title       = models.CharField(max_length=200)
    description = models.TextField()
    type        = models.CharField(max_length=10, choices=TYPE, default="homework")
    classroom   = models.ForeignKey(ClassRoom, on_delete=models.CASCADE)
    teacher     = models.ForeignKey("school.User", on_delete=models.CASCADE, limit_choices_to={"role": "teacher"})
    term        = models.ForeignKey(Term, on_delete=models.CASCADE)
    due_date    = models.DateField()
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "assignments"
        ordering = ["-created_at"]
        indexes = [
            GinIndex(
                name='assign_search_idx',
                fields=['title', 'description'],
                opclasses=['gin_trgm_ops', 'gin_trgm_ops']
            )
        ]

    def __str__(self):
        return f"{self.title} — {self.classroom}"

'''
class DevelopmentReport(models.Model):
    """Teacher's narrative report on a child each term."""
    student          = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="reports")
    term             = models.ForeignKey(Term, on_delete=models.CASCADE)
    written_by       = models.ForeignKey("school.User", on_delete=models.SET_NULL, null=True)
    comment          = models.TextField()
    strengths        = models.TextField(blank=True)
    areas_to_improve = models.TextField(blank=True)
    confidence       = models.PositiveSmallIntegerField(default=3)
    teamwork         = models.PositiveSmallIntegerField(default=3)
    is_published     = models.BooleanField(default=False)
    created_at       = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table        = "development_reports"
        unique_together = ["student", "term"]
        ordering        = ["-created_at"]
        indexes = [
            GinIndex(
                name='report_search_idx',
                fields=['comment', 'strengths', 'areas_to_improve'],
                opclasses=['gin_trgm_ops', 'gin_trgm_ops', 'gin_trgm_ops']
            )
        ]

    def __str__(self):
        return f"Report: {self.student.full_name} — {self.term}"
'''

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


# ---------------------------------------------------------------------------
# Subject Score  (elementary only, one row per subject per report)
# ---------------------------------------------------------------------------

class SubjectScore(models.Model):
    """
    Scores and work-habit ratings for a single subject within an
    elementary AcademicReport.
    """
    report  = models.ForeignKey(AcademicReport, on_delete=models.CASCADE, related_name="subject_scores")
    subject = models.CharField(max_length=20, choices=ELEMENTARY_SUBJECTS)

    # Raw scores
    cat_score  = models.PositiveSmallIntegerField(default=0, help_text="Continuous Assessment score")
    exam_score = models.PositiveSmallIntegerField(default=0, help_text="Examination score")

    # Work-habit index (one rating per habit per subject)
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

    # ------------------------------------------------------------------
    # Computed properties (not stored — derived from scores)
    # ------------------------------------------------------------------

    @property
    def total_score(self) -> int:
        return self.cat_score + self.exam_score

    @property
    def grade(self) -> str:
        t = self.total_score
        if t >= 96: return "A+"
        if t >= 91: return "A"
        if t >= 86: return "B+"
        if t >= 81: return "B"
        if t >= 76: return "C+"
        if t >= 71: return "C"
        if t >= 66: return "D+"
        if t >= 61: return "D"
        return "E"

    def __str__(self):
        return f"{self.get_subject_display()} — {self.report}"