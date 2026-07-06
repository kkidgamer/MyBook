from django.views.generic import ListView, CreateView
from django.urls import reverse_lazy
from rest_framework import viewsets
from .models import Customer
from .serializers import CustomerSerializer


class CustomerListView(ListView):
    model = Customer
    template_name = 'customers/customer_list.html'
    context_object_name = 'customers'
    paginate_by = 10


class CustomerCreateView(CreateView):
    model = Customer
    template_name = 'customers/customer_form.html'
    fields = ['name', 'phone', 'address', 'notes']
    success_url = reverse_lazy('customers:list')


class CustomerViewSet(viewsets.ModelViewSet):
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer
