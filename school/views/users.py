from rest_framework import viewsets, filters, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter, OpenApiTypes, inline_serializer
from rest_framework import serializers as drf_serializers

from ..models import User
from ..serializers import UserSerializer
from .base import DynamicPageSizePagination, is_admin

@extend_schema(tags=["User Management"])
@extend_schema_view(
    list=extend_schema(
        summary="List all users",
        parameters=[
            OpenApiParameter(name="role", description="Filter by role: admin | editor | teacher | non_academic | parent", required=False, type=OpenApiTypes.STR),
            OpenApiParameter(name="page_size", description="Results per page (default 10, max 200)", required=False, type=OpenApiTypes.INT),
        ]
    ),
    retrieve=extend_schema(summary="Retrieve a specific user profile"),
    update=extend_schema(summary="Completely update a user account"),
    partial_update=extend_schema(summary="Partially update user details"),
    destroy=extend_schema(summary="Deactivate a user account (Admin only)"),
)
class UserViewSet(viewsets.ModelViewSet):
    """
    /api/users/
    - Admin creates admin/editor/teacher/non_academic accounts here.
    - Parents register via /api/register/ instead.
    - Editor role: view + edit only; destroy is admin-only.
    """
    queryset           = User.objects.none()
    serializer_class   = UserSerializer
    permission_classes = [IsAuthenticated]
    pagination_class   = DynamicPageSizePagination
    filter_backends    = [filters.SearchFilter]
    search_fields      = ["first_name", "last_name", "email"]

    def get_queryset(self):
        qs   = User.objects.select_related("staff_profile")
        role = self.request.query_params.get("role")
        if role:
            qs = qs.filter(role=role)
        return qs.order_by('-id')

    @extend_schema(
        summary="Create an Admin, Editor, Teacher, or Non-Academic account (Admin only)",
        request=inline_serializer(
            name="AdminCreateUserRequest",
            fields={
                "email":      drf_serializers.EmailField(),
                "first_name": drf_serializers.CharField(),
                "last_name":  drf_serializers.CharField(),
                "phone":      drf_serializers.CharField(required=False),
                "role":       drf_serializers.ChoiceField(choices=["admin", "editor", "teacher", "non_academic"]),
                "password":   drf_serializers.CharField(required=False),
                "staff_profile": drf_serializers.DictField(required=False, help_text="Nested HR data for staff")
            }
        ),
        responses={201: UserSerializer}
    )
    def create(self, request, *args, **kwargs):
        if not is_admin(request.user):
            return Response({"error": "Only admins can create user accounts."}, status=403)

        data = request.data.copy()
        password     = data.pop("password", "ChangeMe123")
        profile_data = data.pop("staff_profile", None)

        user = User.objects.create_user(password=password, **data)

        if profile_data and user.role in ["teacher", "non_academic"]:
            from ..models import StaffProfile
            StaffProfile.objects.create(user=user, **profile_data)

        return Response(UserSerializer(user).data, status=201)

    def destroy(self, request, *args, **kwargs):
        if not is_admin(request.user):
            return Response({"error": "Only admins can deactivate accounts."}, status=403)
        obj           = self.get_object()
        obj.is_active = False
        obj.save(update_fields=["is_active"])
        return Response({"message": "User deactivated."})