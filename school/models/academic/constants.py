# ---------------------------------------------------------------------------
# models/academic/constants.py
# Shared choices and lookup tables used across academic models.
# Import from here — never duplicate these in individual model files.
# ---------------------------------------------------------------------------

WORK_HABIT_CHOICES = [
    ("MS", "Mastered Skills"),
    ("LS", "Learning Skills"),
    ("AC", "Area of Concern"),
    ("NA", "Not Applicable"),
]

ELEMENTARY_SUBJECTS = [
    ("MATH",          "Math"),
    ("ENGLISH",       "English"),
    ("SOCIAL_STUDIES","Social Studies"),
    ("SCIENCE",       "Science"),
    ("CRK",           "C.R.K"),
    ("PHSE",          "P.H.S.E"),
    ("CCA",           "CCA"),
    ("QUANT_RSN",     "Quant Reasoning"),
    ("VERBAL_RSN",    "Verbal Reasoning"),
    ("ICT",           "ICT"),
]
