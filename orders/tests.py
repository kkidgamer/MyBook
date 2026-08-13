from decimal import Decimal
from django.test import TestCase
from rest_framework.test import APITestCase
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token

from books.models import Book, StockMovement
from customers.models import Customer
from orders.models import Order, OrderItem


class OrderAPITestCase(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='tester', password='pass12345')
        self.token = Token.objects.create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')

        self.customer = Customer.objects.create(
            name='Jane Doe', phone='0700000000', address='123 Main St'
        )
        self.book = Book.objects.create(
            title='The Great Gatsby', price=Decimal('500.00'),
            current_quantity=10, min_stock=2, isbn='978-0743273565',
        )

    def make_items(self, book_id, quantity, price='500.00'):
        return [{'book': book_id, 'quantity': quantity, 'price': price}]


class WalkInSaleTests(OrderAPITestCase):
    def test_walk_in_sale_fulfills_and_completes(self):
        response = self.client.post('/api/orders/', {
            'sale_type': 'walk_in',
            'customer': None,
            'payment_received': '1000.00',
            'items': self.make_items(self.book.id, 2),
        }, format='json')

        self.assertEqual(response.status_code, 201, response.data)
        order = response.data
        self.assertEqual(order['sale_type'], 'walk_in')
        self.assertEqual(order['status'], 'Completed')
        self.assertEqual(order['total_amount'], '1000.00')
        self.assertEqual(order['items'][0]['fulfilled_quantity'], 2)
        self.assertFalse(order['has_backorders'])

        # Stock deducted and logged
        self.book.refresh_from_db()
        self.assertEqual(self.book.current_quantity, 8)
        sale_movements = StockMovement.objects.filter(
            book=self.book, reason='sale', quantity_delta=-2
        )
        self.assertEqual(sale_movements.count(), 1)

    def test_walk_in_sale_rejected_when_insufficient_stock(self):
        response = self.client.post('/api/orders/', {
            'sale_type': 'walk_in',
            'items': self.make_items(self.book.id, 99),
        }, format='json')

        self.assertEqual(response.status_code, 400)
        # Nothing changed
        self.book.refresh_from_db()
        self.assertEqual(self.book.current_quantity, 10)
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(StockMovement.objects.count(), 0)

    def test_formal_order_requires_customer(self):
        response = self.client.post('/api/orders/', {
            'sale_type': 'order',
            'customer': None,
            'items': self.make_items(self.book.id, 1),
        }, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('customer', response.data)

    def test_formal_order_allows_backorder(self):
        response = self.client.post('/api/orders/', {
            'sale_type': 'order',
            'customer': self.customer.id,
            'items': self.make_items(self.book.id, 25),
        }, format='json')

        self.assertEqual(response.status_code, 201, response.data)
        order = response.data
        self.assertEqual(order['items'][0]['fulfilled_quantity'], 10)
        self.assertEqual(order['items'][0]['quantity'], 25)
        self.assertTrue(order['has_backorders'])
        self.book.refresh_from_db()
        self.assertEqual(self.book.current_quantity, 0)
        self.assertEqual(
            StockMovement.objects.filter(book=self.book, reason='sale').count(), 1
        )


class StockMovementTests(OrderAPITestCase):
    def test_restock_logs_movement_and_auto_fulfills(self):
        # Create a backordered formal order
        self.client.post('/api/orders/', {
            'sale_type': 'order',
            'customer': self.customer.id,
            'items': self.make_items(self.book.id, 25),
        }, format='json')
        self.book.refresh_from_db()
        self.assertEqual(self.book.current_quantity, 0)

        # Restock 5 — logs restock + auto-fulfill movements
        response = self.client.post(f'/api/books/{self.book.id}/restock/', {
            'quantity': 5, 'notes': 'Replenished shelf',
        }, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['auto_fulfilled'], 5)
        self.book.refresh_from_db()
        self.assertEqual(self.book.current_quantity, 0)  # all 5 went to the backorder

        restock_movements = StockMovement.objects.filter(
            book=self.book, reason='restock', quantity_delta=5
        )
        self.assertEqual(restock_movements.count(), 1)
        self.assertEqual(restock_movements.first().notes, 'Replenished shelf')

    def test_fulfill_action_logs_movement(self):
        order = Order.objects.create(
            sale_type=Order.SaleType.ORDER,
            customer=self.customer,
            total_amount=Decimal('1000.00'),
            payment_received=Decimal('0.00'),
        )
        item = OrderItem.objects.create(
            order=order, book=self.book, quantity=3,
            price=Decimal('500.00'), fulfilled_quantity=0,
        )

        response = self.client.post(f'/api/order-items/{item.id}/fulfill/', {
            'quantity': 3,
        }, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.book.refresh_from_db()
        self.assertEqual(self.book.current_quantity, 7)
        self.assertEqual(
            StockMovement.objects.filter(book=self.book, reason='sale', quantity_delta=-3).count(), 1
        )

    def test_delete_order_restores_stock_and_logs_cancel(self):
        # Simulate a fulfilled sale: stock already deducted by the serializer path
        self.book.current_quantity = 8
        self.book.save(update_fields=['current_quantity'])
        order = Order.objects.create(
            sale_type=Order.SaleType.ORDER,
            customer=self.customer,
            total_amount=Decimal('1000.00'),
            payment_received=Decimal('1000.00'),
        )
        OrderItem.objects.create(
            order=order, book=self.book, quantity=2,
            price=Decimal('500.00'), fulfilled_quantity=2,
        )

        response = self.client.delete(f'/api/orders/{order.id}/')
        self.assertEqual(response.status_code, 204)
        self.book.refresh_from_db()
        self.assertEqual(self.book.current_quantity, 10)  # restored
        self.assertEqual(
            StockMovement.objects.filter(book=self.book, reason='cancel', quantity_delta=2).count(), 1
        )


class OrderFilterTests(OrderAPITestCase):
    def test_filter_by_sale_type(self):
        Order.objects.create(
            sale_type=Order.SaleType.WALK_IN, customer=None,
            status=Order.Status.COMPLETED, total_amount=Decimal('500.00'),
        )
        Order.objects.create(
            sale_type=Order.SaleType.ORDER, customer=self.customer,
            status=Order.Status.PENDING, total_amount=Decimal('1000.00'),
        )

        response = self.client.get('/api/orders/?sale_type=walk_in')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['sale_type'], 'walk_in')
