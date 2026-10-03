from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

# Importación relativa estándar para evitar ImportError en Django
from tickets.views import (
    CartViewSet,
    CustomTokenObtainPairView,
    EventViewSet,
    OrderViewSet,
    RegisterView,
    SectorViewSet,
    TicketViewSet,
    VenueViewSet,
    api_status_view,
)

app_name = 'tickets'

# Configuración del Router para los ViewSets
router = DefaultRouter()
router.register(r'venues', VenueViewSet, basename='venue')
router.register(r'events', EventViewSet, basename='event')
router.register(r'sectors', SectorViewSet, basename='sector')
router.register(r'cart', CartViewSet, basename='cart')
router.register(r'orders', OrderViewSet, basename='order')
router.register(r'tickets', TicketViewSet, basename='ticket')

urlpatterns = [
    # Status / Datos Alumno (Exigido en pauta) -> URL final: /api/status/
    path('status/', api_status_view, name='api_status'),

    # Documentación OpenAPI (Exigido en pauta) -> URL final: /api/schema/ y /api/docs/
    path('schema/', SpectacularAPIView.as_view(), name='schema'),
    path('docs/', SpectacularSwaggerView.as_view(url_name='tickets:schema'), name='swagger-ui'),
    path('redoc/', SpectacularRedocView.as_view(url_name='tickets:schema'), name='redoc'),

    # Endpoints de Autenticación JWT y Registro -> URL final: /api/auth/login/, etc.
    path('auth/register/', RegisterView.as_view(), name='auth_register'),
    path('auth/login/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('auth/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # Endpoints REST del Router -> URL final: /api/events/, /api/orders/, etc.
    path('', include(router.urls)),
]