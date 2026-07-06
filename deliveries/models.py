from django.db import models


class Delivery(models.Model):
    class Status(models.TextChoices):
        PENDING = 'Pending', 'Pending'
        IN_TRANSIT = 'In_Transit', 'In Transit'
        DELIVERED = 'Delivered', 'Delivered'
        FAILED = 'Failed', 'Failed'

    order = models.ForeignKey(
        'orders.Order',
        on_delete=models.CASCADE,
        related_name='deliveries',
    )
    delivery_date = models.DateTimeField()
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    notes = models.TextField(blank=True, default="")
    delivered_by = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-delivery_date']
        verbose_name_plural = 'deliveries'

    def __str__(self):
        return f"Delivery #{self.id} - Order #{self.order.id}"
