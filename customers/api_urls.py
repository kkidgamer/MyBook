from rest_framework.routers import DefaultRouter
from . import views

app_name = 'customers-api'

router = DefaultRouter()
router.register(r'customers', views.CustomerViewSet, basename='customer')

urlpatterns = router.urls
