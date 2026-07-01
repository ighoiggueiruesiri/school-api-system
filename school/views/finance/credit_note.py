from rest_framework import viewsets, filters
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter, OpenApiTypes

from ...models import CreditNote
from ...serializers import CreditNoteSerializer
from ..base import DynamicPageSizePagination, VersionedCacheMixin, is_admin, is_admin_or_editor, is_parent


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

    def create(self, request, *args, **kwargs):
        # Role check must happen before serializer validation. DRF's
        # ModelViewSet.create() validates the payload (raising a 400 on
        # bad/missing data) before perform_create() ever runs, so a
        # permission check placed only in perform_create() can be
        # pre-empted by a 400 from an invalid request, letting
        # unauthorized-but-malformed requests slip past the intended 403.
        if not is_admin_or_editor(request.user):
            raise PermissionDenied("Admin or Editor access required.")
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        serializer.save(logged_by=self.request.user)

    def destroy(self, request, *args, **kwargs):
        if not is_admin(request.user):
            return Response({"error": "Only admins can delete credit notes."}, status=403)
        return super().destroy(request, *args, **kwargs)