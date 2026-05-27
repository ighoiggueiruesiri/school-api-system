"""school/admin.py"""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import (
    User, ClassRoom, Term, Student, Attendance,
    Invoice, Payment, Announcement, Assignment, DevelopmentReport
)

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display   = ["email", "full_name", "role", "is_active", "date_joined"]
    list_filter    = ["role", "is_active"]
    search_fields  = ["email", "first_name", "last_name"]
    ordering       = ["email"]
    fieldsets = (
        (None,            {"fields": ("email", "password")}),
        ("Personal Info", {"fields": ("first_name", "last_name", "phone", "profile_photo")}),
        ("Role",          {"fields": ("role", "is_active", "is_staff", "is_superuser")}),
    )
    add_fieldsets = ((None, {
        "classes": ("wide",),
        "fields":  ("email","first_name","last_name","role","password1","password2"),
    }),)

@admin.register(ClassRoom)
class ClassRoomAdmin(admin.ModelAdmin):
    list_display  = ["name", "level", "teacher", "capacity"]
    ordering      = ["level"]

@admin.register(Term)
class TermAdmin(admin.ModelAdmin):
    list_display  = ["name", "academic_year", "start_date", "end_date", "is_current"]
    list_editable = ["is_current"]

@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display   = ["admission_number", "full_name", "current_class", "is_active"]
    list_filter    = ["current_class", "gender", "is_active"]
    search_fields  = ["first_name", "last_name", "admission_number"]
    filter_horizontal = ["parents"]

@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display  = ["student", "date", "status", "recorded_by"]
    list_filter   = ["status", "term", "date"]
    date_hierarchy = "date"

@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display  = ["invoice_number", "student", "amount", "amount_paid", "status", "due_date"]
    list_filter   = ["status", "term"]
    search_fields = ["invoice_number", "student__first_name", "student__last_name"]

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display  = ["invoice", "amount", "method", "created_at"]
    list_filter   = ["method"]

@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display  = ["title", "audience", "author", "created_at"]
    list_filter   = ["audience"]

@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display  = ["title", "classroom", "teacher", "due_date"]
    list_filter   = ["classroom", "term"]

@admin.register(DevelopmentReport)
class DevelopmentReportAdmin(admin.ModelAdmin):
    list_display  = ["student", "term", "written_by", "is_published"]
    list_filter   = ["is_published", "term"]
    list_editable = ["is_published"]
