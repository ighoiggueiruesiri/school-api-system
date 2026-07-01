from django.db.models import Count, Sum
from rest_framework import viewsets, filters
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter, OpenApiTypes, inline_serializer
from rest_framework import serializers as drf_serializers

from ...models import Expenditure
from ...serializers import ExpenditureSerializer
from ..base import DynamicPageSizePagination, VersionedCacheMixin, is_admin, is_admin_or_editor, is_parent


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

        qs        = Expenditure.objects.select_related("recorded_by")
        category  = self.request.query_params.get("category")
        date_from = self.request.query_params.get("date_from")
        date_to   = self.request.query_params.get("date_to")

        if category:  qs = qs.filter(category=category)
        if date_from: qs = qs.filter(date__gte=date_from)
        if date_to:   qs = qs.filter(date__lte=date_to)
        return qs.order_by("-date", "-created_at")

    def perform_create(self, serializer):
        if not is_admin_or_editor(self.request.user):
            raise PermissionDenied("Admin or Editor access required.")
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