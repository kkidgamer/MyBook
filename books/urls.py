from django.urls import path
from . import views

app_name = 'books'

urlpatterns = [
    path('', views.BookListView.as_view(), name='list'),
    path('add/', views.BookCreateView.as_view(), name='add'),
]
