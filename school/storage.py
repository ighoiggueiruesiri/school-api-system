"""
school/storage.py

Image compression and file size validation.
No external services — pure Pillow + Django local disk storage.

WHAT IT DOES
============
An uploaded phone photo is typically 6-12 MB.
compress_image() shrinks it to ~80 KB before it hits the disk:

  User.profile_photo    -> capped at 400 x 400 px
  Student.profile_photo -> capped at 600 x 600 px

HOW IT CONNECTS TO MODELS
==========================
User.save() and Student.save() in models.py call compress_image()
automatically. You do not call it manually anywhere else.

validate_file_size is attached to the ImageField as a validator,
so Django rejects files over 5 MB before compression even runs.
"""

import io
from PIL import Image, ExifTags
from django.core.files.base import ContentFile
from django.core.exceptions import ValidationError
from django.conf import settings


MAX_DIMENSIONS = {
    "profile": (400, 400),
    "student": (600, 600),
    "general": (1200, 900),
}

JPEG_QUALITY = 82


def _fix_orientation(img):
    """Rotate pixels to match EXIF orientation tag (phone camera fix)."""
    try:
        exif = img._getexif()
        if not exif:
            return img
        for tag_id, val in exif.items():
            if ExifTags.TAGS.get(tag_id) == "Orientation":
                rotations = {3: 180, 6: 270, 8: 90}
                if val in rotations:
                    img = img.rotate(rotations[val], expand=True)
                break
    except Exception:
        pass
    return img


def compress_image(upload, category="general", filename="photo.jpg"):
    """
    Resize + compress an uploaded image. Returns a ContentFile for Django to save.
    Called inside User.save() and Student.save() in models.py.
    """
    max_w, max_h = MAX_DIMENSIONS.get(category, MAX_DIMENSIONS["general"])

    img = Image.open(upload)
    img = _fix_orientation(img)

    if img.mode in ("RGBA", "P", "LA"):
        bg = Image.new("RGB", img.size, (255, 255, 255))
        if img.mode in ("RGBA", "LA"):
            bg.paste(img, mask=img.split()[-1])
        else:
            bg.paste(img)
        img = bg
    elif img.mode != "RGB":
        img = img.convert("RGB")

    img.thumbnail((max_w, max_h), Image.LANCZOS)

    out = io.BytesIO()
    img.save(out, format="JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)
    out.seek(0)

    base = filename.rsplit(".", 1)[0]
    return ContentFile(out.read(), name=f"{base}.jpg")


def validate_file_size(file):
    """
    Validator for ImageField. Rejects files over MAX_UPLOAD_SIZE (default 5 MB).
    Attached to model fields in models.py:
        profile_photo = models.ImageField(validators=[validate_file_size], ...)
    """
    limit = getattr(settings, "MAX_UPLOAD_SIZE", 5 * 1024 * 1024)
    if file.size > limit:
        mb = limit / 1024 / 1024
        raise ValidationError(f"File too large. Maximum allowed size is {mb:.0f} MB.")
