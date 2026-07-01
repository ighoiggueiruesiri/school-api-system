from rest_framework import serializers
from ...models import StaffProfile


class StaffProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model            = StaffProfile
        fields           = "__all__"
        read_only_fields = ["id", "user"]
