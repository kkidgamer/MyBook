from django.contrib import admin
from .models import Book, StockMovement


@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = ['title', 'price', 'current_quantity', 'min_stock', 'isbn']
    list_filter = ['price']
    search_fields = ['title', 'isbn']
    list_editable = ['current_quantity', 'min_stock']

    def save_model(self, request, obj, form, change):
        """Log a StockMovement whenever stock is changed directly in the admin
        (the ledger must never be bypassed)."""
        if change:
            old_qty = Book.objects.get(pk=obj.pk).current_quantity
            delta = obj.current_quantity - old_qty
            if delta != 0:
                StockMovement.objects.create(
                    book=obj,
                    quantity_delta=delta,
                    reason=StockMovement.Reason.ADJUSTMENT,
                    reference=f'Admin edit by {request.user}',
                )
        super().save_model(request, obj, form, change)


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ['book', 'quantity_delta', 'reason', 'reference', 'created_at']
    list_filter = ['reason', 'created_at']
    search_fields = ['book__title', 'book__isbn', 'reference', 'notes']
    readonly_fields = ['book', 'quantity_delta', 'reason', 'reference', 'created_at', 'notes']
