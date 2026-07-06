from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal


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
