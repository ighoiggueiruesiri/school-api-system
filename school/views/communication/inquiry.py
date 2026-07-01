from rest_framework import viewsets, filters
from rest_framework.permissions import IsAuthenticated, AllowAny
from drf_spectacular.utils import extend_schema, extend_schema_view

from ...models import Inquiry
from ...serializers import InquirySerializer
from ..base import DynamicPageSizePagination


@extend_schema(tags=["Lead Capture"])
@extend_schema_view(
    create=extend_schema(
        summary="Submit a public lead/inquiry",
        description="Public endpoint for the website popup. No authentication required.",
        auth=[],
    ),
    list=extend_schema(summary="List all inquiries (Staff only)"),
    retrieve=extend_schema(summary="Get specific inquiry details (Staff only)"),
    update=extend_schema(summary="Update an inquiry (Staff only)"),
    partial_update=extend_schema(summary="Partially update an inquiry (Staff only)"),
    destroy=extend_schema(summary="Delete an inquiry (Staff only)"),
)
class InquiryViewSet(viewsets.ModelViewSet):
    queryset         = Inquiry.objects.all().order_by('-created_at')
    serializer_class = InquirySerializer
    pagination_class = DynamicPageSizePagination
    filter_backends  = [filters.SearchFilter]
    search_fields    = ["parent_name", "email", "phone"]

    def get_permissions(self):
        if self.action == 'create':
            return [AllowAny()]
        return [IsAuthenticated()]
