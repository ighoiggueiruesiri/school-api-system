from .auth import LoginView, RegisterView, LogoutView, MeView
from .users import UserViewSet
from .academic import ClassRoomViewSet, TermViewSet, StudentViewSet, AttendanceViewSet, AssignmentViewSet, DevelopmentReportViewSet
from .finance import InvoiceViewSet, PaymentViewSet, CreditNoteViewSet, ExpenditureViewSet
from .communication import AnnouncementViewSet, InquiryViewSet
from .system import AuditLogViewSet, HealthCheckView