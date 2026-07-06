from rest_framework.routers import DefaultRouter
from . import views

app_name = 'deliveries-api'

router = DefaultRouter()
router.register(r'deliveries', views.DeliveryViewSet, basename='delivery')

urlpatterns = router.urls
