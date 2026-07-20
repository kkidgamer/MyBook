from rest_framework import serializers
from .models import Customer


class CustomerSerializer(serializers.ModelSerializer):
    orders_count = serializers.SerializerMethodField()

    class Meta:
        model = Customer
        fields = '__all__'

    def get_orders_count(self, obj):
        return obj.orders.count()
