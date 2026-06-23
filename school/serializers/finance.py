from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from drf_spectacular.types import OpenApiTypes
from ..models import Invoice, InvoiceLineItem, Payment, CreditNote, Expenditure


class InvoiceLineItemSerializer(serializers.ModelSerializer):
    """
    A single fee row on an invoice.
    `charged_amount` is read-only and equals discounted_amount ?? amount.
    """
    charged_amount = serializers.FloatField(read_only=True)

    class Meta:
        model  = InvoiceLineItem
        fields = [
            "id",
            "description",
            "amount",
            "discounted_amount",
            "charged_amount",
            "sort_order",
        ]
        read_only_fields = ["id", "charged_amount"]


class PaymentSerializer(serializers.ModelSerializer):
    """
    A single instalment or full payment against an invoice.
    """
    paid_by_name    = serializers.SerializerMethodField()
    invoice_number  = serializers.SerializerMethodField()
    student_name    = serializers.SerializerMethodField()
    class_name      = serializers.SerializerMethodField()
    term_name       = serializers.SerializerMethodField()

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


class InvoiceSerializer(serializers.ModelSerializer):
    """
    Full invoice representation including nested line items and payments.
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


class CreditNoteSerializer(serializers.ModelSerializer):
    student_name   = serializers.CharField(source="student.full_name", read_only=True)
    logged_by_name = serializers.CharField(source="logged_by.full_name", read_only=True)

    class Meta:
        model = CreditNote
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


class ExpenditureSerializer(serializers.ModelSerializer):
    """
    School outgoing — salary, utilities, supplies, etc.
    """
    recorded_by_name = serializers.SerializerMethodField()
    category_display = serializers.SerializerMethodField()

    class Meta:
        model = Expenditure
        fields = [
            "id",
            "date",
            "category",
            "category_display",
            "description",
            "amount",
            "reference",
            "notes",
            "recorded_by",
            "recorded_by_name",
            "created_at",
        ]
        read_only_fields = ["id", "recorded_by", "created_at"]

    @extend_schema_field(OpenApiTypes.STR)
    def get_recorded_by_name(self, obj):
        return obj.recorded_by.full_name if obj.recorded_by else None

    @extend_schema_field(OpenApiTypes.STR)
    def get_category_display(self, obj):
        return obj.get_category_display()