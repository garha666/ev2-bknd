"""
URL configuration for ticket_project project.

Rutas principales:
    /            -> Vista HTML base con footer del alumno (EVA-2)
    /admin/      -> Administración de Django
    /api/        -> API REST (ver tickets/urls.py)
"""
from django.contrib import admin
from django.urls import include, path

from tickets.views import home_view

urlpatterns = [
    path('', home_view, name='home'),
    path('admin/', admin.site.urls),
    path('api/', include('tickets.urls')),
]
