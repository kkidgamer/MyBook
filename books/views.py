from django.db import models, transaction
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import Book, StockMovement
from .serializers import BookSerializer, StockMovementSerializer
from orders.models import Order, OrderItem


class BookListView(ListView):
    model = Book
    template_name = 'books/book_list.html'
    context_object_name = 'books'
    paginate_by = 10


class BookCreateView(CreateView):
    model = Book
    template_name = 'books/book_form.html'
    fields = ['title', 'price', 'current_quantity', 'min_stock', 'isbn']
    success_url = reverse_lazy('books:list')


class BookViewSet(viewsets.ModelViewSet):
    queryset = Book.objects.all()
    serializer_class = BookSerializer

    @action(detail=True, methods=['post'])
    def restock(self, request, pk=None):
        """Add stock to a book and auto-fulfill pending backordered items (FIFO).

        Runs inside transaction.atomic() with the Book row locked via
        select_for_update(), and logs StockMovement for the restock as well as
        every auto-fulfillment.
        """
        book = self.get_object()
        quantity = request.data.get('quantity', None)
        notes = str(request.data.get('notes', '')).strip()

        try:
            quantity = int(quantity)
        except (ValueError, TypeError):
            return Response({'error': 'Invalid quantity'}, status=status.HTTP_400_BAD_REQUEST)

        if quantity <= 0:
            return Response({'error': 'Quantity must be positive'}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            # Lock the book row so concurrent sales/restocks can't corrupt stock
            book = Book.objects.select_for_update().get(pk=book.pk)

            # Add to stock first, and log the restock movement
            book.current_quantity += quantity
            book.save(update_fields=['current_quantity', 'updated_at'])
            StockMovement.objects.create(
                book=book,
                quantity_delta=quantity,
                reason=StockMovement.Reason.RESTOCK,
                reference='Manual restock',
                notes=notes,
            )

            # Find unfulfilled order items for this book (FIFO by order date)
            pending_items = OrderItem.objects.filter(
                book=book,
                fulfilled_quantity__lt=models.F('quantity'),
                order__status__in=['Pending', 'Paid', 'Ready_For_Delivery', 'Ready_For_Pickup'],
            ).select_related('order').order_by('order__order_date')

            total_fulfilled = 0
            fulfilled_orders = set()

            for item in pending_items:
                remaining = item.quantity - item.fulfilled_quantity
                can_fulfill = min(remaining, book.current_quantity)

                if can_fulfill <= 0:
                    break

                # Deduct from the locked inventory
                book.current_quantity -= can_fulfill
                item.fulfilled_quantity += can_fulfill
                item.save(update_fields=['fulfilled_quantity'])
                StockMovement.objects.create(
                    book=book,
                    quantity_delta=-can_fulfill,
                    reason=StockMovement.Reason.SALE,
                    reference=f'Order #{item.order_id} (auto-fulfill on restock)',
                )
                total_fulfilled += can_fulfill
                fulfilled_orders.add(item.order_id)

            if total_fulfilled > 0:
                book.save(update_fields=['current_quantity', 'updated_at'])

        # Re-evaluate status for every affected order
        if fulfilled_orders:
            for order in Order.objects.filter(id__in=fulfilled_orders):
                order.auto_transition_status()

        serializer = self.get_serializer(book)
        return Response({
            'book': serializer.data,
            'auto_fulfilled': total_fulfilled,
            'backorders_remaining': OrderItem.objects.filter(
                book=book,
                fulfilled_quantity__lt=models.F('quantity'),
                order__status__in=['Pending', 'Paid', 'Ready_For_Delivery', 'Ready_For_Pickup'],
            ).count(),
        })

    @action(detail=True, methods=['get'])
    def movements(self, request, pk=None):
        """Return the stock movement history for a book (newest first)."""
        book = self.get_object()
        movements = StockMovement.objects.filter(book=book)[:100]
        return Response(StockMovementSerializer(movements, many=True).data)
