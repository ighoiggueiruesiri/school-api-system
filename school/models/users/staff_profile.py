from django.db import models

from .user import User


class StaffProfile(models.Model):
    """
    Extended HR bio-data for Teachers and Non-Academic Staff.
    Maps directly to the official Employee Bio-Data form.
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="staff_profile")

    # Demographics
    date_of_birth   = models.DateField(null=True, blank=True)
    gender          = models.CharField(
        max_length=10, choices=[("male", "Male"), ("female", "Female")], blank=True
    )
    marital_status  = models.CharField(max_length=20, blank=True)
    nationality     = models.CharField(max_length=50, default="Nigerian")
    state_of_origin = models.CharField(max_length=50, blank=True)
    lga             = models.CharField(max_length=50, blank=True)
    home_address    = models.TextField(blank=True)

    # Emergency & Family
    spouse_name                = models.CharField(max_length=100, blank=True)
    spouse_phone               = models.CharField(max_length=20, blank=True)
    emergency_contact_name     = models.CharField(max_length=100, blank=True)
    emergency_contact_phone    = models.CharField(max_length=20, blank=True)
    emergency_contact_relation = models.CharField(max_length=50, blank=True)

    # Education & Experience
    highest_qualification = models.CharField(max_length=100, blank=True)
    institution           = models.CharField(max_length=150, blank=True)
    year_attained         = models.CharField(max_length=4, blank=True)
    previous_employer     = models.CharField(max_length=150, blank=True)
    previous_job_title    = models.CharField(max_length=100, blank=True)
    teaching_philosophy   = models.TextField(blank=True,
                                             help_text="Teaching approach and philosophy")

    # Medical
    blood_group        = models.CharField(max_length=5, blank=True)
    genotype           = models.CharField(max_length=5, blank=True)
    medical_conditions = models.TextField(blank=True)

    # Guarantors (Shortees)
    shortee_1_name  = models.CharField(max_length=100, blank=True)
    shortee_1_phone = models.CharField(max_length=20, blank=True)
    shortee_2_name  = models.CharField(max_length=100, blank=True)
    shortee_2_phone = models.CharField(max_length=20, blank=True)

    class Meta:
        db_table = "staff_profiles"

    def __str__(self):
        return f"Staff Profile: {self.user.full_name}"
