from django.contrib import admin
from .models import Book


@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = ['title', 'price', 'current_quantity', 'min_stock', 'isbn']
    list_filter = ['price']
    search_fields = ['title', 'isbn']
    list_editable = ['current_quantity', 'min_stock']
