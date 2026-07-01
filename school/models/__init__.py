# ---------------------------------------------------------------------------
# models/__init__.py
# Single re-export point. Every other module in this project imports from
# here — never from a sub-package directly.
#
# Adding a new model: create its file in the right sub-package, export it
# from that package's __init__.py, then add it to this file.
# ---------------------------------------------------------------------------

from .users import (
    UserRole,
    UserManager,
    User,
    StaffProfile,
)
from .academic import (
    WORK_HABIT_CHOICES,
    ELEMENTARY_SUBJECTS,
    ClassRoom,
    Term,
    Student,
    Attendance,
    Assignment,
    AcademicReport,
    SubjectScore,
)
from .finance import (
    Invoice,
    InvoiceLineItem,
    Payment,
    CreditNote,
    Expenditure,
)
from .communication import (
    Announcement,
    Inquiry,
)
from .system import (
    AuditLog,
)

__all__ = [
    # users
    "UserRole", "UserManager", "User", "StaffProfile",
    # academic
    "WORK_HABIT_CHOICES", "ELEMENTARY_SUBJECTS",
    "ClassRoom", "Term", "Student",
    "Attendance", "Assignment",
    "AcademicReport", "SubjectScore",
    # finance
    "Invoice", "InvoiceLineItem", "Payment", "CreditNote", "Expenditure",
    # communication
    "Announcement", "Inquiry",
    # system
    "AuditLog",
]