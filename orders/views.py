from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import Order, OrderItem
from .serializers import OrderSerializer, OrderItemSerializer


class OrderViewSet(viewsets.ModelViewSet):
    queryset = Order.objects.all()
    serializer_class = OrderSerializer

    def perform_destroy(self, instance):
        """Stock is not affected on delete — just remove the order."""
        instance.delete()


class OrderItemViewSet(viewsets.ModelViewSet):
    queryset = OrderItem.objects.all()
    serializer_class = OrderItemSerializer

    @action(detail=True, methods=['post'])
    def fulfill(self, request, pk=None):
        """Mark an order item as fulfilled: deduct from book stock and increase fulfilled_quantity."""
        item = self.get_object()
        qty = request.data.get('quantity', None)

        if qty is None:
            qty = item.quantity - item.fulfilled_quantity

        try:
            qty = int(qty)
        except (ValueError, TypeError):
            return Response({'error': 'Invalid quantity'}, status=status.HTTP_400_BAD_REQUEST)

        if qty <= 0:
            return Response({'error': 'Quantity must be positive'}, status=status.HTTP_400_BAD_REQUEST)

        remaining = item.quantity - item.fulfilled_quantity
        if qty > remaining:
            return Response(
                {'error': f'Only {remaining} more can be fulfilled for this item.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check stock availability and deduct
        book = item.book
        if book.current_quantity < qty:
            return Response(
                {'error': f'Only {book.current_quantity} of "{book.title}" in stock, cannot fulfill {qty}.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        book.current_quantity -= qty
        book.save(update_fields=['current_quantity'])

        item.fulfilled_quantity += qty
        item.save(update_fields=['fulfilled_quantity'])

        # Re-evaluate parent order's status after fulfillment
        item.order.auto_transition_status()

        serializer = self.get_serializer(item)
        return Response(serializer.data)
