from rest_framework.routers import DefaultRouter
from . import views

app_name = 'orders-api'

router = DefaultRouter()
router.register(r'orders', views.OrderViewSet, basename='order')
router.register(r'order-items', views.OrderItemViewSet, basename='order-item')

urlpatterns = router.urls
