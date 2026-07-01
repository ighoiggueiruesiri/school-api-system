import uuid
from django.db.models import Count, Q, Sum
from rest_framework import viewsets, filters
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter, OpenApiTypes, inline_serializer
from rest_framework import serializers as drf_serializers

from ...models import Invoice
from ...serializers import InvoiceSerializer
from ..base import DynamicPageSizePagination, VersionedCacheMixin, is_admin, is_admin_or_editor, is_parent


@extend_schema(tags=["Financial Invoices Accounting"])
@extend_schema_view(
    list=extend_schema(
        summary="List invoices",
        parameters=[
            OpenApiParameter(name="student",   description="Filter by student ID",    required=False, type=OpenApiTypes.STR),
            OpenApiParameter(name="term",      description="Filter by term ID",       required=False, type=OpenApiTypes.INT),
            OpenApiParameter(name="status",    description="unpaid | partial | paid", required=False, type=OpenApiTypes.STR),
            OpenApiParameter(name="page_size", description="Results per page",        required=False, type=OpenApiTypes.INT),
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
        qs   = Invoice.objects.select_related(
            "student__current_class", "term"
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
            # NOTE: must be a DRF APIException subclass so the exception
            # handler converts it into a 403 response. A bare PermissionError
            # is not caught by DRF and results in an unhandled 500.
            raise PermissionDenied("Admin or Editor access required.")
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