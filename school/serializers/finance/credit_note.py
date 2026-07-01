from rest_framework import serializers
from ...models import CreditNote


class CreditNoteSerializer(serializers.ModelSerializer):
    student_name   = serializers.CharField(source="student.full_name",  read_only=True)
    logged_by_name = serializers.CharField(source="logged_by.full_name", read_only=True)

    class Meta:
        model  = CreditNote
        fields = [
            "id",
            "student",
            "student_name",
            "amount",
            "reference",
            "notes",
            "is_used",
            "logged_by",
            "logged_by_name",
            "created_at",
        ]
        read_only_fields = ["id", "logged_by", "created_at"]
