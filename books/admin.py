from django.contrib import admin
from .models import Book, StockMovement


@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = ['title', 'price', 'current_quantity', 'min_stock', 'isbn']
    list_filter = ['price']
    search_fields = ['title', 'isbn']
    list_editable = ['current_quantity', 'min_stock']

    def save_model(self, request, obj, form, change):
        """Log a StockMovement whenever stock changes in the admin — on create
        (opening balance) as well as edits (the ledger must never be bypassed)."""
        old_qty = 0
        if change:
            old_qty = Book.objects.get(pk=obj.pk).current_quantity
        super().save_model(request, obj, form, change)
        delta = obj.current_quantity - old_qty
        if delta != 0:
            StockMovement.objects.create(
                book=obj,
                quantity_delta=delta,
                reason=StockMovement.Reason.ADJUSTMENT,
                reference=f'Admin edit by {request.user}' if change else f'Created by {request.user}',
            )


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ['book', 'quantity_delta', 'reason', 'reference', 'created_at']
    list_filter = ['reason', 'created_at']
    search_fields = ['book__title', 'book__isbn', 'reference', 'notes']
    readonly_fields = ['book', 'quantity_delta', 'reason', 'reference', 'created_at', 'notes']
