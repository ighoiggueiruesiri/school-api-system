from rest_framework import serializers
from django.contrib.auth import get_user_model

from ...models import StaffProfile
from .staff_profile import StaffProfileSerializer

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    staff_profile = StaffProfileSerializer(required=False)

    class Meta:
        model  = User
        fields = [
            "id", "email", "first_name", "last_name",
            "phone", "role", "profile_photo",
            "date_joined", "is_active",
            "staff_profile",
        ]
        read_only_fields = ["id", "role", "date_joined"]

    def update(self, instance, validated_data):
        profile_data = validated_data.pop("staff_profile", None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if profile_data is not None and instance.role in ["teacher", "non_academic"]:
            StaffProfile.objects.update_or_create(user=instance, defaults=profile_data)

        return instance
