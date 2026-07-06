from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal


class Order(models.Model):
    class Status(models.TextChoices):
        PENDING = 'Pending', 'Pending'
        PAID = 'Paid', 'Paid'
        READY_FOR_DELIVERY = 'Ready_For_Delivery', 'Ready for Delivery'
        DELIVERED = 'Delivered', 'Delivered'
        CANCELLED = 'Cancelled', 'Cancelled'

    customer = models.ForeignKey(
        'customers.Customer',
        on_delete=models.CASCADE,
        related_name='orders',
    )
    order_date = models.DateTimeField(auto_now_add=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    total_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
    )
    payment_received = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
    )
    payment_notes = models.TextField(blank=True, default="")

    class Meta:
        ordering = ['-order_date']

    def __str__(self):
        return f"Order #{self.id} - {self.customer.name}"

    @property
    def balance_due(self):
        return self.total_amount - self.payment_received

    @property
    def is_fully_paid(self):
        return self.balance_due <= Decimal('0.00')

    def auto_transition_status(self):
        """Automatically transition status based on payment and fulfillment.
        Does not override Cancelled or Delivered."""
        if self.status in ('Cancelled', 'Delivered'):
            return
        if self.is_fully_paid:
            all_fulfilled = all(
                item.fulfilled_quantity >= item.quantity
                for item in self.items.all()
            )
            new_status = self.Status.READY_FOR_DELIVERY if all_fulfilled else self.Status.PAID
            if new_status != self.status:
                self.status = new_status
                self.save(update_fields=['status'])


class OrderItem(models.Model):
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name='items',
    )
    book = models.ForeignKey(
        'books.Book',
        on_delete=models.CASCADE,
        related_name='order_items',
    )
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
    )
    fulfilled_quantity = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.quantity}x {self.book.title} (Order #{self.order.id})"

    @property
    def subtotal(self):
        return self.price * self.quantity
