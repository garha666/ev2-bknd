"""Rutas de las vistas HTML (frontend server-rendered)."""

from django.urls import path

from . import web_views

app_name = 'web'

urlpatterns = [
    # Catálogo público
    path('', web_views.home, name='home'),
    path('eventos/<int:pk>/', web_views.event_detail, name='event_detail'),

    # Carro persistente
    path('carro/', web_views.cart_detail, name='cart_detail'),
    path('carro/agregar/<int:sector_id>/', web_views.add_to_cart, name='add_to_cart'),
    path('carro/quitar/<int:item_id>/', web_views.remove_from_cart, name='remove_from_cart'),

    # Checkout, pago y entradas
    path('checkout/', web_views.checkout, name='checkout'),
    path('mis-ordenes/', web_views.my_orders, name='my_orders'),
    path('mis-ordenes/<int:pk>/pagar/', web_views.pay_order, name='pay_order'),
    path('mis-ordenes/<int:pk>/cancelar/', web_views.cancel_order, name='cancel_order'),
    path('mis-entradas/', web_views.my_tickets, name='my_tickets'),

    # Autenticación por sesión
    path('login/', web_views.login_view, name='login'),
    path('logout/', web_views.logout_view, name='logout'),
    path('registro/', web_views.register_view, name='register'),

    # Panel del organizador
    path('panel/', web_views.panel, name='panel'),
    path('panel/ordenes/<int:pk>/estado/', web_views.panel_order_status, name='panel_order_status'),
    path('panel/eventos/crear/', web_views.panel_event_create, name='panel_event_create'),
    path('panel/sectores/crear/', web_views.panel_sector_create, name='panel_sector_create'),
]
