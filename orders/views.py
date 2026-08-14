from datetime import timedelta
from django.db import transaction
from django.db.models import Sum, Count, Q, F, DecimalField
from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import Order, OrderItem
from .serializers import OrderSerializer, OrderItemSerializer
from books.models import Book, StockMovement


class OrderViewSet(viewsets.ModelViewSet):
    queryset = Order.objects.all()
    serializer_class = OrderSerializer

    def get_queryset(self):
        """Support filtering by sale type (?sale_type=walk_in|order) and
        today's sales (?today=true)."""
        queryset = Order.objects.all()
        sale_type = self.request.query_params.get('sale_type')
        if sale_type in Order.SaleType.values:
            queryset = queryset.filter(sale_type=sale_type)
        if self.request.query_params.get('today') == 'true':
            today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
            queryset = queryset.filter(order_date__gte=today_start)
        return queryset

    def perform_destroy(self, instance):
        """Deleting an order restores any fulfilled stock back into inventory
        and logs a positive StockMovement (reason 'cancel') for traceability.
        Stock restore and delete happen in the same transaction."""
        with transaction.atomic():
            for item in instance.items.select_related('book'):
                if item.fulfilled_quantity > 0:
                    book = Book.objects.select_for_update().get(pk=item.book_id)
                    book.current_quantity += item.fulfilled_quantity
                    book.save(update_fields=['current_quantity', 'updated_at'])
                    StockMovement.objects.create(
                        book=book,
                        quantity_delta=item.fulfilled_quantity,
                        reason=StockMovement.Reason.CANCEL,
                        reference=f'Order #{instance.id} (deleted)',
                    )
            instance.delete()

    @action(detail=False, methods=['get'])
    def sales_report(self, request):
        """Return aggregated sales report data."""
        now = timezone.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = today_start - timedelta(days=today_start.weekday())
        month_start = today_start.replace(day=1)

        # Base queryset: exclude cancelled orders for revenue calcs
        active_orders = Order.objects.exclude(status='Cancelled')

        # Revenue aggregates
        total_revenue = active_orders.aggregate(
            total=Sum('total_amount', default=0)
        )['total']

        today_revenue = active_orders.filter(
            order_date__gte=today_start
        ).aggregate(total=Sum('total_amount', default=0))['total']

        week_revenue = active_orders.filter(
            order_date__gte=week_start
        ).aggregate(total=Sum('total_amount', default=0))['total']

        month_revenue = active_orders.filter(
            order_date__gte=month_start
        ).aggregate(total=Sum('total_amount', default=0))['total']

        # Payment received vs balance
        payment_stats = Order.objects.aggregate(
            total_received=Sum('payment_received', default=0),
            total_pending=Sum(
                F('total_amount') - F('payment_received'),
                output_field=DecimalField(),
                default=0
            )
        )

        # Order status breakdown
        status_counts = {
            status: Order.objects.filter(status=status).count()
            for status, _ in Order.Status.choices
        }

        # Sale type breakdown (orders vs walk-ins)
        sale_type_breakdown = {}
        for st, _ in Order.SaleType.choices:
            qs = active_orders.filter(sale_type=st)
            today_qs = qs.filter(order_date__gte=today_start)
            sale_type_breakdown[st] = {
                'count': qs.count(),
                'revenue': float(qs.aggregate(total=Sum('total_amount', default=0))['total'] or 0),
                'today_count': today_qs.count(),
                'today_revenue': float(today_qs.aggregate(total=Sum('total_amount', default=0))['total'] or 0),
            }

        # Top selling books
        top_books = OrderItem.objects.values(
            'book__title', 'book__id'
        ).annotate(
            quantity_sold=Sum('quantity'),
            fulfilled=Sum('fulfilled_quantity'),
            revenue=Sum(F('price') * F('quantity'), output_field=DecimalField()),
        ).order_by('-quantity_sold')[:10]

        # Daily revenue for last 30 days
        thirty_days_ago = today_start - timedelta(days=30)
        daily_revenue = []
        for i in range(30):
            day = today_start - timedelta(days=i)
            next_day = day + timedelta(days=1)
            rev = active_orders.filter(
                order_date__gte=day,
                order_date__lt=next_day
            ).aggregate(total=Sum('total_amount', default=0))['total']
            daily_revenue.append({
                'date': day.strftime('%Y-%m-%d'),
                'revenue': float(rev),
            })
        daily_revenue.reverse()

        return Response({
            'total_revenue': float(total_revenue),
            'today_revenue': float(today_revenue),
            'week_revenue': float(week_revenue),
            'month_revenue': float(month_revenue),
            'total_received': float(payment_stats['total_received']),
            'pending_balance': float(payment_stats['total_pending']),
            'total_orders': Order.objects.count(),
            'status_breakdown': status_counts,
            'sale_type_breakdown': sale_type_breakdown,
            'top_books': [
                {
                    'id': b['book__id'],
                    'title': b['book__title'],
                    'quantity_sold': b['quantity_sold'],
                    'fulfilled': b['fulfilled'],
                    'revenue': float(b['revenue']),
                }
                for b in top_books if b['book__title']
            ],
            'daily_revenue': daily_revenue,
            'generated_at': now.isoformat(),
        })


class OrderItemViewSet(viewsets.ModelViewSet):
    """Read-only access to order items, plus the dedicated fulfill action.

    Creating/editing/deleting order items is intentionally disabled: items must
    be managed through the order endpoints so stock deductions and totals stay
    consistent (any direct write here would bypass the StockMovement ledger).
    POST is kept in http_method_names only because the fulfill action needs it;
    the list-collection POST (create) is rejected below.
    """
    queryset = OrderItem.objects.all()
    serializer_class = OrderItemSerializer
    http_method_names = ['get', 'head', 'options', 'post']

    def create(self, request, *args, **kwargs):
        """Reject direct order-item creation — items must go through the order
        endpoints so stock deductions, totals, and the ledger stay consistent."""
        return Response(
            {
                'detail': (
                    'Order items cannot be created directly. Add or edit items '
                    'through the order endpoint so stock stays consistent.'
                )
            },
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

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

        # Check stock availability and deduct (row locked, atomic)
        with transaction.atomic():
            book = Book.objects.select_for_update().get(pk=item.book_id)
            if book.current_quantity < qty:
                return Response(
                    {'error': f'Only {book.current_quantity} of "{book.title}" in stock, cannot fulfill {qty}.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            book.current_quantity -= qty
            book.save(update_fields=['current_quantity', 'updated_at'])
            StockMovement.objects.create(
                book=book,
                quantity_delta=-qty,
                reason=StockMovement.Reason.SALE,
                reference=f'Order #{item.order_id} (fulfill)',
            )

            item.fulfilled_quantity += qty
            item.save(update_fields=['fulfilled_quantity'])

        # Re-evaluate parent order's status after fulfillment
        item.order.auto_transition_status()

        serializer = self.get_serializer(item)
        return Response(serializer.data)
