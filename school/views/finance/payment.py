from rest_framework import viewsets, filters
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.serializers import as_serializer_error
from django.core.exceptions import ValidationError as DjangoValidationError
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter, OpenApiTypes

from ...models import Payment
from ...serializers import PaymentSerializer
from ..base import DynamicPageSizePagination, VersionedCacheMixin, is_admin, is_admin_or_editor, is_parent


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
    # A payment write updates the related Invoice's amount_paid/status
    # directly on the model (see perform_create below), so the invoice
    # cache must be invalidated too or stale balances/status keep serving.
    related_cache_resources = ("invoices",)
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
        # NOTE: must raise a DRF APIException subclass, not the builtin
        # PermissionError. The builtin exception is not caught by DRF's
        # exception handler and previously bubbled up as an unhandled
        # 500 Internal Server Error instead of a 403 Forbidden response.
        if not is_admin_or_editor(self.request.user):
            raise PermissionDenied("Admin or Editor access required.")
        try:
            serializer.save(paid_by=self.request.user)
        except DjangoValidationError as exc:
            # Payment.save() calls self.full_clean(), which raises Django's
            # core ValidationError (not DRF's). DRF's exception handler
            # doesn't recognize that type, so left uncaught it previously
            # bubbled up as an unhandled 500 instead of a 400 Bad Request
            # with the field-level error message (e.g. exceeding the
            # invoice balance). Re-raise as DRF's ValidationError so it's
            # handled normally.
            raise ValidationError(as_serializer_error(exc))

    def destroy(self, request, *args, **kwargs):
        if not is_admin(request.user):
            return Response({"error": "Only admins can delete payment records."}, status=403)
        return super().destroy(request, *args, **kwargs)