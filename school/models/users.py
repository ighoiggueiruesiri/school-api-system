import uuid
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone
from django.contrib.postgres.indexes import GinIndex
from ..storage import validate_file_size, compress_image

class UserRole(models.TextChoices):
    ADMIN   = "admin",   "Admin"
    EDITOR  = "editor",  "Editor"  
    TEACHER = "teacher", "Teacher"
    NON_ACADEMIC = "non_academic", "Non-Academic Staff"
    PARENT  = "parent",  "Parent"


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra):
        if not email:
            raise ValueError("Email is required")
        email = self.normalize_email(email)
        user  = self.model(email=email, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra):
        extra["is_staff"]     = True
        extra["is_superuser"] = True
        extra["role"]         = UserRole.ADMIN
        return self.create_user(email, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    """Single login table for every role."""
    id            = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email         = models.EmailField(unique=True)
    first_name    = models.CharField(max_length=100)
    last_name     = models.CharField(max_length=100)
    phone         = models.CharField(max_length=20, blank=True)
    role          = models.CharField(max_length=20, choices=UserRole.choices, default=UserRole.PARENT)
    profile_photo = models.ImageField(
        upload_to="profiles/", null=True, blank=True,
        validators=[validate_file_size]
    )
    is_active     = models.BooleanField(default=True)
    is_staff      = models.BooleanField(default=False)
    date_joined   = models.DateTimeField(default=timezone.now)

    objects        = UserManager()
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    class Meta:
        db_table = "users"
        indexes = [
            GinIndex(
                name='user_search_idx',
                fields=['first_name', 'last_name', 'email'],
                opclasses=['gin_trgm_ops', 'gin_trgm_ops', 'gin_trgm_ops']
            )
        ]

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.role})"

    def save(self, *args, **kwargs):
        if self.profile_photo and hasattr(self.profile_photo, 'file'):
            try:
                compressed = compress_image(
                    self.profile_photo, "profile",
                    self.profile_photo.name or "profile.jpg"
                )
                self.profile_photo.save("profile.jpg", compressed, save=False)
            except Exception:
                pass  # compression failed — save original
        super().save(*args, **kwargs)

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"


class StaffProfile(models.Model):
    """
    Extended HR bio-data specifically for Teachers and Non-Academic Staff.
    Maps directly to the official Employee Bio-Data form.
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="staff_profile")
    
    # Demographics
    date_of_birth   = models.DateField(null=True, blank=True)
    gender          = models.CharField(max_length=10, choices=[("male", "Male"), ("female", "Female")], blank=True)
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
    teaching_philosophy   = models.TextField(blank=True, help_text="Teaching approach and philosophy")

    # Medical
    blood_group        = models.CharField(max_length=5, blank=True)
    genotype           = models.CharField(max_length=5, blank=True)
    medical_conditions = models.TextField(blank=True)

    # Shortees (Guarantors)
    shortee_1_name  = models.CharField(max_length=100, blank=True)
    shortee_1_phone = models.CharField(max_length=20, blank=True)
    shortee_2_name  = models.CharField(max_length=100, blank=True)
    shortee_2_phone = models.CharField(max_length=20, blank=True)

    class Meta:
        db_table = "staff_profiles"

    def __str__(self):
        return f"Staff Profile: {self.user.full_name}"