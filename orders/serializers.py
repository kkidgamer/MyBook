from django.db import transaction
from django.db.models import F
from rest_framework import serializers
from .models import Order, OrderItem
from books.models import Book, StockMovement
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
    customer_name = serializers.CharField(source='customer.name', read_only=True, allow_null=True)
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

    def validate(self, attrs):
        """Formal orders require a customer; walk-in sales must not be backordered."""
        sale_type = attrs.get('sale_type', getattr(self.instance, 'sale_type', Order.SaleType.ORDER))
        if sale_type == Order.SaleType.ORDER:
            customer = attrs.get('customer', getattr(self.instance, 'customer', None))
            if customer is None:
                raise serializers.ValidationError(
                    {'customer': 'Customer is required for formal orders.'}
                )
        return attrs

    def _apply_stock_change(self, book, delta, reason, reference, notes=''):
        """Apply a locked stock change and record its StockMovement."""
        book.current_quantity += delta
        book.save(update_fields=['current_quantity', 'updated_at'])
        StockMovement.objects.create(
            book=book,
            quantity_delta=delta,
            reason=reason,
            reference=reference,
            notes=notes,
        )

    def _create_items(self, order, items_data, is_walk_in):
        """Create order items under an atomic transaction.

        Formal orders auto-fulfill from available stock and leave the rest as
        backorder. Walk-in sales must be fully fulfillable or the whole sale
        is rejected.
        """
        total = Decimal('0.00')
        for item_data in items_data:
            book = Book.objects.select_for_update().get(pk=item_data['book'].pk)
            quantity = item_data['quantity']
            price = item_data['price']

            available = book.current_quantity
            can_fulfill = min(quantity, available)

            if is_walk_in and can_fulfill < quantity:
                raise serializers.ValidationError(
                    {'items': (
                        f'Not enough stock for "{book.title}": {quantity} requested, '
                        f'only {available} available. Walk-in sales cannot be backordered.'
                    )}
                )

            if can_fulfill > 0:
                self._apply_stock_change(
                    book, -can_fulfill, StockMovement.Reason.SALE,
                    reference=f'Order #{order.id}',
                )

            OrderItem.objects.create(
                order=order,
                book=book,
                quantity=quantity,
                price=price,
                fulfilled_quantity=can_fulfill,
            )
            total += price * quantity
        return total

    def create(self, validated_data):
        """Create an order (formal or walk-in) with stock safety.

        All quantity changes happen inside transaction.atomic() with the Book
        row locked via select_for_update(), and every change is logged in
        StockMovement.
        """
        items_data = validated_data.pop('items', [])
        is_walk_in = validated_data.get('sale_type') == Order.SaleType.WALK_IN

        with transaction.atomic():
            order = Order.objects.create(**validated_data)
            total = self._create_items(order, items_data, is_walk_in)
            order.total_amount = total
            order.save(update_fields=['total_amount'])

            if is_walk_in:
                # Walk-ins are immediate counter sales — jump straight to Completed.
                order.status = Order.Status.COMPLETED
                order.save(update_fields=['status'])
            else:
                order.auto_transition_status()
        return order

    def update(self, instance, validated_data):
        """Update order fields and items — restores old fulfilled stock first
        (logging the restore), then re-creates items with fresh auto-fulfillment.
        All inside an atomic transaction with locked Book rows."""
        items_data = validated_data.pop('items', None)
        new_sale_type = validated_data.get('sale_type', instance.sale_type)
        is_walk_in = new_sale_type == Order.SaleType.WALK_IN

        with transaction.atomic():
            if is_walk_in:
                # Walk-ins always stay in the Completed state.
                validated_data['status'] = Order.Status.COMPLETED

            for attr, value in validated_data.items():
                setattr(instance, attr, value)
            instance.save()

            if items_data is not None:
                # Restore stock from old fulfilled items before replacing them
                old_items = instance.items.select_related('book')
                for old_item in old_items:
                    if old_item.fulfilled_quantity > 0:
                        book = Book.objects.select_for_update().get(pk=old_item.book_id)
                        self._apply_stock_change(
                            book,
                            old_item.fulfilled_quantity,
                            StockMovement.Reason.CANCEL,
                            reference=f'Order #{instance.id} (item edit)',
                        )
                old_items.delete()

                total = self._create_items(instance, items_data, is_walk_in)
                instance.total_amount = total
                instance.save(update_fields=['total_amount'])

            if is_walk_in:
                # Walk-ins must always be fully fulfilled — reject the update
                # otherwise (e.g. converting a backordered order to walk-in).
                if instance.items.filter(fulfilled_quantity__lt=F('quantity')).exists():
                    raise serializers.ValidationError(
                        {'items': 'Walk-in sales must be fully fulfilled — not enough stock available for all items.'}
                    )
                instance.status = Order.Status.COMPLETED
                instance.save(update_fields=['status'])
            else:
                instance.auto_transition_status()
        return instance
