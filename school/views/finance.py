import uuid
from django.db.models import Count, Q, Sum
from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter, OpenApiTypes, inline_serializer
from rest_framework import serializers as drf_serializers

from ..models import Invoice, Payment, CreditNote, Expenditure
from ..serializers import InvoiceSerializer, PaymentSerializer, CreditNoteSerializer, ExpenditureSerializer
from .base import DynamicPageSizePagination, VersionedCacheMixin, is_admin, is_admin_or_editor, is_parent

@extend_schema(tags=["Financial Invoices Accounting"])
@extend_schema_view(
    list=extend_schema(
        summary="List invoices",
        parameters=[
            OpenApiParameter(name="student",   description="Filter by student ID",  required=False, type=OpenApiTypes.STR),
            OpenApiParameter(name="term",      description="Filter by term ID",     required=False, type=OpenApiTypes.INT),
            OpenApiParameter(name="status",    description="unpaid | partial | paid", required=False, type=OpenApiTypes.STR),
            OpenApiParameter(name="page_size", description="Results per page",      required=False, type=OpenApiTypes.INT),
        ]
    ),
    create=extend_schema(summary="Generate an invoice (Admin or Editor)"),
    destroy=extend_schema(summary="Delete an invoice (Admin only)"),
)
class InvoiceViewSet(VersionedCacheMixin, viewsets.ModelViewSet):
    cache_resource     = "invoices"
    queryset           = Invoice.objects.none()
    serializer_class   = InvoiceSerializer
    permission_classes = [IsAuthenticated]
    pagination_class   = DynamicPageSizePagination
    filter_backends    = [filters.SearchFilter]
    search_fields      = ["invoice_number", "description", "student__first_name", "student__last_name"]

    def _cache_discriminator(self, request) -> str:
        if is_parent(request.user):
            return f"parent:{request.user.id}"
        return "admin_editor"

    def get_queryset(self):
        user = self.request.user
        qs = Invoice.objects.select_related(
            "student__current_class",
            "term",
        ).prefetch_related("payments", "line_items")

        if is_parent(user):
            qs = qs.filter(student__parents=user)
        student = self.request.query_params.get("student")
        term    = self.request.query_params.get("term")
        status_ = self.request.query_params.get("status")
        if student: qs = qs.filter(student_id=student)
        if term:    qs = qs.filter(term_id=term)
        if status_: qs = qs.filter(status=status_)
        return qs.order_by('-id')

    def perform_create(self, serializer):
        if not is_admin_or_editor(self.request.user):
            raise PermissionError("Admin or Editor access required.")
        student    = serializer.validated_data["student"]
        term       = serializer.validated_data["term"]
        short_uuid = uuid.uuid4().hex[:6].upper()
        num        = f"INV-{student.admission_number}-{term.id}-{short_uuid}"
        serializer.save(invoice_number=num)

    def destroy(self, request, *args, **kwargs):
        if not is_admin(request.user):
            return Response({"error": "Only admins can delete invoices."}, status=403)
        return super().destroy(request, *args, **kwargs)

    @extend_schema(
        summary="Financial totals summary",
        parameters=[OpenApiParameter(name="student", description="Student ID", required=False, type=OpenApiTypes.STR)],
        responses={200: inline_serializer(
            name="InvoiceSummaryResponse",
            fields={
                "total_billed":  drf_serializers.FloatField(),
                "total_paid":    drf_serializers.FloatField(),
                "balance":       drf_serializers.FloatField(),
                "invoice_count": drf_serializers.IntegerField(),
                "unpaid_count":  drf_serializers.IntegerField(),
            }
        )}
    )
    @action(detail=False, methods=["get"])
    def summary(self, request):
        qs         = self.get_queryset()
        student_id = request.query_params.get("student")
        if student_id:
            qs = qs.filter(student_id=student_id)

        totals = qs.aggregate(
            billed=Sum("amount"),
            paid=Sum("amount_paid"),
            invoice_count=Count("id"),
            unpaid_count=Count("id", filter=Q(status__in=["unpaid", "partial"])),
        )
        billed = totals["billed"] or 0
        paid   = totals["paid"]   or 0
        return Response({
            "total_billed":  billed,
            "total_paid":    paid,
            "balance":       billed - paid,
            "invoice_count": totals["invoice_count"],
            "unpaid_count":  totals["unpaid_count"],
        })


@extend_schema(tags=["Financial Payments Records Processing"])
@extend_schema_view(
    list=extend_schema(
        summary="List payment records",
        parameters=[
            OpenApiParameter(name="invoice",   description="Filter by invoice ID", required=False, type=OpenApiTypes.STR),
            OpenApiParameter(name="page_size", description="Results per page",     required=False, type=OpenApiTypes.INT),
        ]
    ),
    create=extend_schema(summary="Record a payment (Admin or Editor)"),
    destroy=extend_schema(summary="Delete a payment record (Admin only)"),
)
class PaymentViewSet(VersionedCacheMixin, viewsets.ModelViewSet):
    cache_resource     = "payments"
    queryset           = Payment.objects.none()
    serializer_class   = PaymentSerializer
    permission_classes = [IsAuthenticated]
    pagination_class   = DynamicPageSizePagination
    filter_backends    = [filters.SearchFilter]
    search_fields      = ["reference", "notes", "invoice__invoice_number"]

    def _cache_discriminator(self, request) -> str:
        if is_parent(request.user):
            return f"parent:{request.user.id}"
        return "admin_editor"

    def get_queryset(self):
        qs = Payment.objects.select_related(
            "invoice__student__current_class",
            "invoice__term",
            "paid_by",
        )
        if is_parent(self.request.user):
            qs = qs.filter(invoice__student__parents=self.request.user)
        invoice = self.request.query_params.get("invoice")
        if invoice:
            qs = qs.filter(invoice_id=invoice)
        return qs.order_by('-id')

    def perform_create(self, serializer):
        if not is_admin_or_editor(self.request.user):
            raise PermissionError("Admin or Editor access required.")
        serializer.save(paid_by=self.request.user)

    def destroy(self, request, *args, **kwargs):
        if not is_admin(request.user):
            return Response({"error": "Only admins can delete payment records."}, status=403)
        return super().destroy(request, *args, **kwargs)


@extend_schema(tags=["Financial Credit Notes Processing"])
@extend_schema_view(
    list=extend_schema(
        summary="List credit notes",
        parameters=[
            OpenApiParameter(name="student",   description="Filter by student ID", required=False, type=OpenApiTypes.STR),
            OpenApiParameter(name="page_size", description="Results per page",     required=False, type=OpenApiTypes.INT),
        ]
    ),
    create=extend_schema(summary="Log a credit note (Admin or Editor)"),
    destroy=extend_schema(summary="Delete a credit note (Admin only)"),
)
class CreditNoteViewSet(VersionedCacheMixin, viewsets.ModelViewSet):
    cache_resource     = "credit_notes"
    queryset           = CreditNote.objects.none()
    serializer_class   = CreditNoteSerializer
    permission_classes = [IsAuthenticated]
    pagination_class   = DynamicPageSizePagination
    filter_backends    = [filters.SearchFilter]
    search_fields      = ["reference", "notes", "student__first_name", "student__last_name"]

    def _cache_discriminator(self, request) -> str:
        if is_parent(request.user):
            return f"parent:{request.user.id}"
        return "admin_editor"

    def get_queryset(self):
        user = self.request.user
        qs   = CreditNote.objects.select_related("student", "logged_by")
        if is_parent(user):
            return qs.filter(student__parents=user)
        student = self.request.query_params.get("student")
        if student:
            qs = qs.filter(student_id=student)
        return qs.order_by('-id')

    def perform_create(self, serializer):
        if not is_admin_or_editor(self.request.user):
            raise PermissionError("Admin or Editor access required.")
        serializer.save(logged_by=self.request.user)

    def destroy(self, request, *args, **kwargs):
        if not is_admin(request.user):
            return Response({"error": "Only admins can delete credit notes."}, status=403)
        return super().destroy(request, *args, **kwargs)


@extend_schema(tags=["Financial Expenditures"])
@extend_schema_view(
    list=extend_schema(
        summary="List expenditures",
        parameters=[
            OpenApiParameter(name="category",  description="Filter by category slug", required=False, type=OpenApiTypes.STR),
            OpenApiParameter(name="date_from", description="YYYY-MM-DD start date",   required=False, type=OpenApiTypes.DATE),
            OpenApiParameter(name="date_to",   description="YYYY-MM-DD end date",     required=False, type=OpenApiTypes.DATE),
            OpenApiParameter(name="page_size", description="Results per page",        required=False, type=OpenApiTypes.INT),
        ]
    ),
    create=extend_schema(summary="Record an expenditure (Admin or Editor)"),
    destroy=extend_schema(summary="Delete an expenditure record (Admin only)"),
)
class ExpenditureViewSet(VersionedCacheMixin, viewsets.ModelViewSet):
    cache_resource     = "expenditures"
    queryset           = Expenditure.objects.none()
    serializer_class   = ExpenditureSerializer
    permission_classes = [IsAuthenticated]
    pagination_class   = DynamicPageSizePagination
    filter_backends    = [filters.SearchFilter]
    search_fields      = ["description", "reference", "notes"]

    def _cache_discriminator(self, request) -> str:
        return "staff"

    def get_queryset(self):
        user = self.request.user
        if is_parent(user):
            return Expenditure.objects.none()

        qs = Expenditure.objects.select_related("recorded_by")
        category  = self.request.query_params.get("category")
        date_from = self.request.query_params.get("date_from")
        date_to   = self.request.query_params.get("date_to")

        if category:  qs = qs.filter(category=category)
        if date_from: qs = qs.filter(date__gte=date_from)
        if date_to:   qs = qs.filter(date__lte=date_to)

        return qs.order_by("-date", "-created_at")

    def perform_create(self, serializer):
        if not is_admin_or_editor(self.request.user):
            raise PermissionError("Admin or Editor access required.")
        serializer.save(recorded_by=self.request.user)

    def destroy(self, request, *args, **kwargs):
        if not is_admin(request.user):
            return Response({"error": "Only admins can delete expenditure records."}, status=403)
        return super().destroy(request, *args, **kwargs)

    @extend_schema(
        summary="Expenditure totals and category breakdown",
        parameters=[
            OpenApiParameter(name="date_from", description="YYYY-MM-DD", required=False, type=OpenApiTypes.DATE),
            OpenApiParameter(name="date_to",   description="YYYY-MM-DD", required=False, type=OpenApiTypes.DATE),
        ],
        responses={200: inline_serializer(
            name="ExpenditureSummaryResponse",
            fields={
                "total_spent": drf_serializers.FloatField(),
                "count":       drf_serializers.IntegerField(),
                "by_category": drf_serializers.ListField(child=drf_serializers.DictField()),
            }
        )}
    )
    @action(detail=False, methods=["get"])
    def summary(self, request):
        qs     = self.get_queryset()
        totals = qs.aggregate(total=Sum("amount"), count=Count("id"))

        by_category = list(
            qs.values("category")
              .annotate(total=Sum("amount"), count=Count("id"))
              .order_by("-total")
        )

        return Response({
            "total_spent": totals["total"] or 0,
            "count":       totals["count"] or 0,
            "by_category": by_category,
        })