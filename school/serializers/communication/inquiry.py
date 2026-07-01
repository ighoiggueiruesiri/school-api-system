from rest_framework import serializers
from ...models import Inquiry


class InquirySerializer(serializers.ModelSerializer):
    class Meta:
        model            = Inquiry
        fields           = [
            "id",
            "parent_name",
            "email",
            "phone",
            "interested_class",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]