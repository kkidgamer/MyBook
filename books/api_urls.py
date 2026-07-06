from rest_framework.routers import DefaultRouter
from . import views

app_name = 'books-api'

router = DefaultRouter()
router.register(r'books', views.BookViewSet, basename='book')

urlpatterns = router.urls
