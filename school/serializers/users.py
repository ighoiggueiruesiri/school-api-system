from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth import get_user_model
from ..models import StaffProfile

User = get_user_model()

class LoginSerializer(TokenObtainPairSerializer):
    """Adds user info to the login response so the frontend knows the role."""
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
    """Parent self-registration."""
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
        return User.objects.create_user(
            role="parent", **validated_data
        )

class StaffProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = StaffProfile
        fields = "__all__"
        read_only_fields = ["id", "user"]

class UserSerializer(serializers.ModelSerializer):
    staff_profile = StaffProfileSerializer(required=False)

    class Meta:
        model  = User
        fields = ["id","email","first_name","last_name","phone","role","profile_photo","date_joined","is_active", "staff_profile"]
        read_only_fields = ["id","role","date_joined"]

    def update(self, instance, validated_data):
        profile_data = validated_data.pop("staff_profile", None)
        
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if profile_data is not None and instance.role in ["teacher", "non_academic"]:
            StaffProfile.objects.update_or_create(user=instance, defaults=profile_data)

        return instance