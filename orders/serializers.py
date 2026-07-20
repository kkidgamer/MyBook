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
        """Validate that books are selected."""
        for i, item_data in enumerate(items_data):
            if item_data.get('book') is None:
                raise serializers.ValidationError([f"Item #{i + 1}: no book selected."])
        return items_data

    def create(self, validated_data):
        """Create order and items — auto-fulfills from available stock.
        Items with insufficient stock become backorders."""
        items_data = validated_data.pop('items', [])
        order = Order.objects.create(**validated_data)
        total = Decimal('0.00')
        for item_data in items_data:
            book = item_data['book']
            quantity = item_data['quantity']
            price = item_data['price']

            # Auto-fulfill from available stock
            available = book.current_quantity
            can_fulfill = min(quantity, available)
            if can_fulfill > 0:
                book.current_quantity -= can_fulfill
                book.save(update_fields=['current_quantity'])

            OrderItem.objects.create(
                order=order,
                book=book,
                quantity=quantity,
                price=price,
                fulfilled_quantity=can_fulfill,
            )
            total += price * quantity

        order.total_amount = total
        order.save(update_fields=['total_amount'])
        order.auto_transition_status()
        return order

    def update(self, instance, validated_data):
        """Update order fields and items — restores old fulfillment stock first,
        then re-creates items with fresh auto-fulfillment."""
        items_data = validated_data.pop('items', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if items_data is not None:
            # Restore stock from old fulfilled items before replacing them
            old_items = instance.items.all()
            for old_item in old_items:
                if old_item.fulfilled_quantity > 0:
                    old_item.book.current_quantity += old_item.fulfilled_quantity
                    old_item.book.save(update_fields=['current_quantity'])

            # Delete old items and create new ones with auto-fulfillment
            old_items.delete()
            total = Decimal('0.00')
            for item_data in items_data:
                book = item_data['book']
                quantity = item_data['quantity']
                price = item_data['price']

                available = book.current_quantity
                can_fulfill = min(quantity, available)
                if can_fulfill > 0:
                    book.current_quantity -= can_fulfill
                    book.save(update_fields=['current_quantity'])

                OrderItem.objects.create(
                    order=instance,
                    book=book,
                    quantity=quantity,
                    price=price,
                    fulfilled_quantity=can_fulfill,
                )
                total += price * quantity

            instance.total_amount = total
            instance.save(update_fields=['total_amount'])

        instance.auto_transition_status()
        return instance
