from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from drf_spectacular.types import OpenApiTypes

from ...models import Invoice, InvoiceLineItem
from .invoice_line_item import InvoiceLineItemSerializer
from .payment           import PaymentSerializer


class InvoiceSerializer(serializers.ModelSerializer):
    """
    Full invoice with nested line items and payments.

    - `line_items` are writeable: sent on create/update, fully replaced on update.
    - `payments`   are read-only: returned for display, never written here.
    - `balance`    is a read-only model property.
    """
    balance      = serializers.FloatField(read_only=True)
    student_name = serializers.SerializerMethodField()
    class_name   = serializers.SerializerMethodField()
    term_name    = serializers.SerializerMethodField()
    payments     = PaymentSerializer(many=True, read_only=True)
    line_items   = InvoiceLineItemSerializer(many=True, required=False)

    class Meta:
        model  = Invoice
        fields = [
            "id",
            "invoice_number",
            "student",
            "student_name",
            "class_name",
            "term",
            "term_name",
            "description",
            "notes",
            "amount",
            "amount_paid",
            "balance",
            "status",
            "due_date",
            "line_items",
            "payments",
            "created_at",
        ]
        read_only_fields = ["id", "invoice_number", "amount_paid", "status", "created_at"]

    @extend_schema_field(OpenApiTypes.STR)
    def get_student_name(self, obj):
        return obj.student.full_name

    @extend_schema_field(OpenApiTypes.STR)
    def get_class_name(self, obj):
        cls = obj.student.current_class
        return cls.name if cls else None

    @extend_schema_field(OpenApiTypes.STR)
    def get_term_name(self, obj):
        return str(obj.term)

    def create(self, validated_data):
        line_items_data = validated_data.pop("line_items", [])
        invoice = Invoice.objects.create(**validated_data)
        for idx, item in enumerate(line_items_data):
            item.setdefault("sort_order", idx)
            InvoiceLineItem.objects.create(invoice=invoice, **item)
        return invoice

    def update(self, instance, validated_data):
        line_items_data = validated_data.pop("line_items", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if line_items_data is not None:
            instance.line_items.all().delete()
            for idx, item in enumerate(line_items_data):
                item.setdefault("sort_order", idx)
                InvoiceLineItem.objects.create(invoice=instance, **item)
        return instance
