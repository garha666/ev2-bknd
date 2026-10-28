"""
URL configuration for ticket_project project.

Rutas principales:
    /            -> Frontend HTML (catálogo, carro, órdenes, entradas, panel)
    /admin/      -> Administración de Django
    /api/        -> API REST con JWT (ver tickets/urls.py)
"""
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('tickets.urls')),
    path('', include('tickets.web_urls')),
]
