from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth import get_user_model

User = get_user_model()


class LoginSerializer(TokenObtainPairSerializer):
    """Extends the JWT response to include role + full_name on login."""

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["role"]      = user.role
        token["full_name"] = user.full_name
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        data["user"] = {
            "id":        str(self.user.id),
            "email":     self.user.email,
            "full_name": self.user.full_name,
            "role":      self.user.role,
        }
        return data


class RegisterSerializer(serializers.Serializer):
    """Parent self-registration — creates a User with role='parent'."""
    email      = serializers.EmailField()
    password   = serializers.CharField(write_only=True, min_length=6)
    first_name = serializers.CharField()
    last_name  = serializers.CharField()
    phone      = serializers.CharField(required=False, allow_blank=True)

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Email already registered.")
        return value.lower()

    def create(self, validated_data):
        return User.objects.create_user(role="parent", **validated_data)
