from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.tokens import RefreshToken
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers as drf_serializers

from ..serializers import LoginSerializer, RegisterSerializer, UserSerializer

@extend_schema(tags=["Authentication"])
class LoginView(TokenObtainPairView):
    """POST /api/login/ — returns access + refresh JWT tokens."""
    serializer_class   = LoginSerializer
    permission_classes = [AllowAny]
    throttle_classes   = [ScopedRateThrottle]
    throttle_scope     = 'auth'

@extend_schema(tags=["Authentication"])
class RegisterView(APIView):
    """POST /api/register/ — parent self-registration, no login needed."""
    permission_classes = [AllowAny]
    throttle_classes   = [ScopedRateThrottle]
    throttle_scope     = 'auth'

    @extend_schema(
        summary="Parent Self-Registration",
        request=RegisterSerializer,
        responses={201: inline_serializer(
            name="RegisterSuccessResponse",
            fields={"message": drf_serializers.CharField(), "email": drf_serializers.EmailField()}
        )}
    )
    def post(self, request):
        s = RegisterSerializer(data=request.data)
        if s.is_valid():
            user = s.save()
            return Response(
                {"message": "Account created. You can now log in.", "email": user.email},
                status=status.HTTP_201_CREATED
            )
        return Response(s.errors, status=status.HTTP_400_BAD_REQUEST)

@extend_schema(tags=["Authentication"])
class LogoutView(APIView):
    """POST /api/logout/ — blacklists the refresh token."""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Logout / Blacklist Token",
        request=inline_serializer(name="LogoutRequest", fields={"refresh": drf_serializers.CharField()}),
        responses={200: inline_serializer(name="LogoutResponse", fields={"message": drf_serializers.CharField()})}
    )
    def post(self, request):
        try:
            RefreshToken(request.data["refresh"]).blacklist()
            return Response({"message": "Logged out."})
        except Exception:
            return Response({"error": "Invalid token."}, status=400)

@extend_schema(tags=["Authentication"])
class MeView(APIView):
    """GET /api/me/ — returns the currently logged-in user's profile."""
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Retrieve logged-in user details", responses={200: UserSerializer})
    def get(self, request):
        return Response(UserSerializer(request.user, context={"request": request}).data)

    @extend_schema(summary="Partially update logged-in user profile", request=UserSerializer, responses={200: UserSerializer})
    def patch(self, request):
        s = UserSerializer(request.user, data=request.data, partial=True, context={"request": request})
        if s.is_valid():
            s.save()
            return Response(s.data)
        return Response(s.errors, status=400)