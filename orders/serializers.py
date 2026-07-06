from django.db.models import F
from rest_framework import serializers
from .models import Order, OrderItem
from decimal import Decimal


class OrderItemSerializer(serializers.ModelSerializer):
    subtotal = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    book_title = serializers.CharField(source='book.title', read_only=True)

    class Meta:
        model = OrderItem
        fields = '__all__'
        read_only_fields = ['order', 'fulfilled_quantity']


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True)
    customer_name = serializers.CharField(source='customer.name', read_only=True)
    balance_due = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    is_fully_paid = serializers.BooleanField(read_only=True)
    has_backorders = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = '__all__'

    def get_has_backorders(self, obj):
        """An order has backorders if any item's fulfilled_quantity < ordered quantity."""
        return obj.items.filter(fulfilled_quantity__lt=F('quantity')).exists()

    def validate_items(self, items_data):
        """Only validate that books are selected — stock is not checked."""
        for i, item_data in enumerate(items_data):
            if item_data.get('book') is None:
                raise serializers.ValidationError([f"Item #{i + 1}: no book selected."])
        return items_data

    def create(self, validated_data):
        """Create order and items — stock is NOT deducted. Items start unfulfilled."""
        items_data = validated_data.pop('items', [])
        order = Order.objects.create(**validated_data)
        for item_data in items_data:
            OrderItem.objects.create(order=order, **item_data)
        if items_data:
            total = sum(
                (item['price'] or Decimal('0')) * (item['quantity'] or 0)
                for item in items_data
            )
            order.total_amount = total
            order.save(update_fields=['total_amount'])
        order.auto_transition_status()
        return order

    def update(self, instance, validated_data):
        """Update order fields — stock is never touched. Auto-transitions status."""
        items_data = validated_data.pop('items', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if items_data is not None:
            instance.items.all().delete()
            for item_data in items_data:
                OrderItem.objects.create(order=instance, **item_data)
            total = sum(
                (item['price'] or Decimal('0')) * (item['quantity'] or 0)
                for item in items_data
            )
            instance.total_amount = total
            instance.save(update_fields=['total_amount'])
        # Auto-transition status based on payment and fulfillment
        instance.auto_transition_status()
        return instance
