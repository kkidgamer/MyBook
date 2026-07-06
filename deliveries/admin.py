from django.contrib import admin
from .models import Delivery


@admin.register(Delivery)
class DeliveryAdmin(admin.ModelAdmin):
    list_display = ['id', 'order', 'delivery_date', 'status', 'delivered_by']
    list_filter = ['status', 'delivery_date']
    search_fields = ['order__id', 'delivered_by']
