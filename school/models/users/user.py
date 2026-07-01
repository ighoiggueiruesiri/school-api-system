import uuid
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone
from django.contrib.postgres.indexes import GinIndex

# NOTE: validate_file_size and compress_image are imported LAZILY inside
# save() below.  Importing them at module level caused a circular import:
#   school.models → school.models.users → school.models.users.user
#   → school.storage → school.models  (cycle!)
# Django's app registry hit school.models.users while it was still being
# initialised, so UserRole had not yet been bound → the startup error.


class UserRole(models.TextChoices):
    ADMIN        = "admin",        "Admin"
    EDITOR       = "editor",       "Editor"
    TEACHER      = "teacher",      "Teacher"
    NON_ACADEMIC = "non_academic", "Non-Academic Staff"
    PARENT       = "parent",       "Parent"


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
        # validator imported lazily in save() — see note above
    )
    is_active   = models.BooleanField(default=True)
    is_staff    = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD  = "email"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    class Meta:
        db_table = "users"
        indexes  = [
            GinIndex(
                name="user_search_idx",
                fields=["first_name", "last_name", "email"],
                opclasses=["gin_trgm_ops", "gin_trgm_ops", "gin_trgm_ops"],
            )
        ]

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.role})"

    def save(self, *args, **kwargs):
        if self.profile_photo and hasattr(self.profile_photo, "file"):
            # Lazy import keeps school.storage out of the module-level
            # import graph and eliminates the circular dependency.
            from ...storage import validate_file_size, compress_image  # noqa: F401
            try:
                compressed = compress_image(
                    self.profile_photo, "profile",
                    self.profile_photo.name or "profile.jpg",
                )
                self.profile_photo.save("profile.jpg", compressed, save=False)
            except Exception:
                pass  # compression failed — save original
        super().save(*args, **kwargs)

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"