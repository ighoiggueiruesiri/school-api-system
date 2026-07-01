# ---------------------------------------------------------------------------
# serializers/__init__.py
# Single re-export point. Every other module in this project imports from
# here — never from a sub-package directly.
#
# Adding a new serializer: create its file in the right sub-package, export
# it from that package's __init__.py, then add it here.
# ---------------------------------------------------------------------------

from .users import (
    LoginSerializer,
    RegisterSerializer,
    StaffProfileSerializer,
    UserSerializer,
)
from .academic import (
    ClassRoomSerializer,
    TermSerializer,
    StudentSerializer,
    AttendanceSerializer,
    BulkAttendanceSerializer,
    AssignmentSerializer,
    SubjectScoreSerializer,
    AcademicReportSerializer,
    AcademicReportListSerializer,
)
from .finance import (
    InvoiceLineItemSerializer,
    PaymentSerializer,
    InvoiceSerializer,
    CreditNoteSerializer,
    ExpenditureSerializer,
)
from .communication import (
    AnnouncementSerializer,
    InquirySerializer,
)
from .system import (
    AuditLogSerializer,
)

__all__ = [
    # users
    "LoginSerializer", "RegisterSerializer",
    "StaffProfileSerializer", "UserSerializer",
    # academic
    "ClassRoomSerializer", "TermSerializer", "StudentSerializer",
    "AttendanceSerializer", "BulkAttendanceSerializer", "AssignmentSerializer",
    "SubjectScoreSerializer", "AcademicReportSerializer", "AcademicReportListSerializer",
    # finance
    "InvoiceLineItemSerializer", "PaymentSerializer", "InvoiceSerializer",
    "CreditNoteSerializer", "ExpenditureSerializer",
    # communication
    "AnnouncementSerializer", "InquirySerializer",
    # system
    "AuditLogSerializer",
]