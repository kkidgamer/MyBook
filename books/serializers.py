from django.db.models import F
from rest_framework import serializers
from .models import Book


class BookSerializer(serializers.ModelSerializer):
    is_low_stock = serializers.BooleanField(read_only=True)
    has_pending_backorders = serializers.SerializerMethodField()

    class Meta:
        model = Book
        fields = '__all__'

    def get_has_pending_backorders(self, obj):
        return obj.order_items.filter(
            fulfilled_quantity__lt=F('quantity'),
            order__status__in=['Pending', 'Paid', 'Ready_For_Delivery'],
        ).exists()
