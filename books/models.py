from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal


class StockMovement(models.Model):
    """Ledger of every quantity change to a book's stock.

    Every update to Book.current_quantity must be accompanied by a
    StockMovement row so stock can always be traced (sales, restocks,
    cancellations, returns, adjustments).
    """

    class Reason(models.TextChoices):
        SALE = 'sale', 'Sale'
        RESTOCK = 'restock', 'Restock'
        ADJUSTMENT = 'adjustment', 'Adjustment'
        RETURN = 'return', 'Return'
        CANCEL = 'cancel', 'Cancel'

    book = models.ForeignKey(
        'Book',
        on_delete=models.CASCADE,
        related_name='stock_movements',
    )
    quantity_delta = models.IntegerField()  # negative for sale, positive for restock/return/cancel
    reason = models.CharField(
        max_length=20,
        choices=Reason.choices,
        default=Reason.ADJUSTMENT,
    )
    reference = models.CharField(max_length=255, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-created_at', '-id']

    def __str__(self):
        return f"{self.quantity_delta:+d} x {self.book.title} ({self.reason})"


class Book(models.Model):
    title = models.CharField(max_length=255)
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
    )
    current_quantity = models.PositiveIntegerField(default=0)
    min_stock = models.PositiveIntegerField(default=0)
    isbn = models.CharField(
        max_length=20,
        unique=True,
        blank=True,
        null=True,
        help_text="Optional unique ISBN identifier (ISBN-10 or ISBN-13)",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['title']

    def __str__(self):
        return self.title

    def is_low_stock(self):
        """Check if current stock is at or below minimum stock level."""
        return self.current_quantity <= self.min_stock
