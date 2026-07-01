from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter, OpenApiTypes

from ...models import Term
from ...serializers import TermSerializer
from ..base import DynamicPageSizePagination, VersionedCacheMixin, is_admin, is_admin_or_editor


@extend_schema(tags=["Academic Calendar Terms"])
@extend_schema_view(
    list=extend_schema(
        summary="List all academic terms",
        parameters=[OpenApiParameter(name="page_size", description="Results per page", required=False, type=OpenApiTypes.INT)]
    ),
    create=extend_schema(summary="Create an academic term (Admin or Editor)"),
    retrieve=extend_schema(summary="Retrieve a specific term"),
    update=extend_schema(summary="Update a term (Admin or Editor)"),
    partial_update=extend_schema(summary="Partially update a term (Admin or Editor)"),
    destroy=extend_schema(summary="Delete a term (Admin only)"),
)
class TermViewSet(VersionedCacheMixin, viewsets.ModelViewSet):
    cache_resource     = "terms"
    queryset           = Term.objects.all().order_by('-id')
    serializer_class   = TermSerializer
    permission_classes = [IsAuthenticated]
    pagination_class   = DynamicPageSizePagination

    def _cache_discriminator(self, request) -> str:
        return "all"

    def create(self, request, *args, **kwargs):
        if not is_admin_or_editor(request.user):
            return Response({"error": "Admin or Editor access required."}, status=403)
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        if not is_admin_or_editor(request.user):
            return Response({"error": "Admin or Editor access required."}, status=403)
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        if not is_admin(request.user):
            return Response({"error": "Only admins can delete terms."}, status=403)
        return super().destroy(request, *args, **kwargs)

    @extend_schema(summary="Get the active term", responses={200: TermSerializer})
    @action(detail=False, methods=["get"])
    def current(self, request):
        term = Term.objects.filter(is_current=True).first()
        if not term:
            return Response({"error": "No current term set."}, status=404)
        return Response(TermSerializer(term).data)
