from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from drf_spectacular.types import OpenApiTypes

from ...models import Payment


class PaymentSerializer(serializers.ModelSerializer):
    """A single instalment or full payment recorded against an invoice."""
    paid_by_name   = serializers.SerializerMethodField()
    invoice_number = serializers.SerializerMethodField()
    student_name   = serializers.SerializerMethodField()
    class_name     = serializers.SerializerMethodField()
    term_name      = serializers.SerializerMethodField()

    class Meta:
        model  = Payment
        fields = [
            "id",
            "invoice",
            "invoice_number",
            "student_name",
            "class_name",
            "term_name",
            "amount",
            "method",
            "reference",
            "receipt_number",
            "paid_date",
            "paid_by",
            "paid_by_name",
            "notes",
            "created_at",
        ]
        read_only_fields = ["id", "paid_by", "created_at"]

    @extend_schema_field(OpenApiTypes.STR)
    def get_paid_by_name(self, obj):
        return obj.paid_by.full_name if obj.paid_by else None

    @extend_schema_field(OpenApiTypes.STR)
    def get_invoice_number(self, obj):
        return obj.invoice.invoice_number

    @extend_schema_field(OpenApiTypes.STR)
    def get_student_name(self, obj):
        return obj.invoice.student.full_name

    @extend_schema_field(OpenApiTypes.STR)
    def get_class_name(self, obj):
        cls = obj.invoice.student.current_class
        return cls.name if cls else None

    @extend_schema_field(OpenApiTypes.STR)
    def get_term_name(self, obj):
        return str(obj.invoice.term)
