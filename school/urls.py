"""school/urls.py"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView
from .views import (
    LoginView, RegisterView, LogoutView, MeView,
    UserViewSet, ClassRoomViewSet, TermViewSet, StudentViewSet,
    AttendanceViewSet, InvoiceViewSet, PaymentViewSet, CreditNoteViewSet,
    AnnouncementViewSet, AssignmentViewSet, DevelopmentReportViewSet,
    AuditLogViewSet, HealthCheckView, InquiryViewSet, ExpenditureViewSet
)

router = DefaultRouter()
router.register("users",         UserViewSet,             basename="users")
router.register("classrooms",    ClassRoomViewSet,        basename="classrooms")
router.register("terms",         TermViewSet,             basename="terms")
router.register("students",      StudentViewSet,          basename="students")
router.register("attendance",    AttendanceViewSet,       basename="attendance")
router.register("invoices",      InvoiceViewSet,          basename="invoices")
router.register("payments",      PaymentViewSet,          basename="payments")
router.register("credit-notes",  CreditNoteViewSet,       basename="credit-notes")
router.register("announcements", AnnouncementViewSet,     basename="announcements")
router.register("assignments",   AssignmentViewSet,       basename="assignments")
router.register("reports",       DevelopmentReportViewSet, basename="reports")
router.register("audit-logs",    AuditLogViewSet,         basename="audit-logs")
router.register("inquiries",     InquiryViewSet,          basename="inquiries")
router.register("expenditures",  ExpenditureViewSet,      basename='expenditure')

urlpatterns = [

    path("",         HealthCheckView.as_view(),  name="health"),
    
    # Auth
    path("login/",          LoginView.as_view(),        name="login"),
    path("register/",       RegisterView.as_view(),     name="register"),
    path("logout/",         LogoutView.as_view(),       name="logout"),
    path("token/refresh/",  TokenRefreshView.as_view(), name="token-refresh"),
    path("me/",             MeView.as_view(),           name="me"),
    
    # Everything else via router
    path("",                include(router.urls)),
]
