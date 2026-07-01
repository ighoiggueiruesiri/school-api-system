from rest_framework import serializers
from ...models import InvoiceLineItem


class InvoiceLineItemSerializer(serializers.ModelSerializer):
    """
    A single fee row on an invoice.
    `charged_amount` is a read-only model property: discounted_amount ?? amount.
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
