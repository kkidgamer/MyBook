from django.contrib import admin
from django.urls import path, include
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView

urlpatterns = [
    path('admin/', admin.site.urls),
    # Template-based UI
    path('books/', include('books.urls')),
    path('customers/', include('customers.urls')),
    # REST API
    path('api/', include('books.api_urls')),
    path('api/', include('customers.api_urls')),
    path('api/', include('orders.api_urls')),
    path('api/', include('deliveries.api_urls')),
    path('api/auth/', include('rest_framework.urls')),
    # API documentation
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
]
