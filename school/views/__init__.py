from .auth    import LoginView, RegisterView, LogoutView, MeView
from .users   import UserViewSet

from .academic import (
    ClassRoomViewSet,
    TermViewSet,
    StudentViewSet,
    AttendanceViewSet,
    AssignmentViewSet,
    AcademicReportViewSet,
)
from .finance import (
    InvoiceViewSet,
    PaymentViewSet,
    CreditNoteViewSet,
    ExpenditureViewSet,
)
from .communication import (
    AnnouncementViewSet,
    InquiryViewSet,
)
from .system import (
    AuditLogViewSet,
    HealthCheckView,
)

__all__ = [
    # auth
    "LoginView", "RegisterView", "LogoutView", "MeView",
    # users
    "UserViewSet",
    # academic
    "ClassRoomViewSet", "TermViewSet", "StudentViewSet",
    "AttendanceViewSet", "AssignmentViewSet", "AcademicReportViewSet",
    # finance
    "InvoiceViewSet", "PaymentViewSet", "CreditNoteViewSet", "ExpenditureViewSet",
    # communication
    "AnnouncementViewSet", "InquiryViewSet",
    # system
    "AuditLogViewSet", "HealthCheckView",
]