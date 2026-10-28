"""
Filtros de consulta (django-filter) para el catálogo.

Permiten filtrar eventos por recinto, fecha y rango de precios de sus sectores,
y sectores por evento, rango de precio y disponibilidad de stock.
"""

import django_filters

from .models import Event, Sector


class EventFilter(django_filters.FilterSet):
    """Filtros del catálogo de eventos."""

    date_from = django_filters.IsoDateTimeFilter(field_name='date', lookup_expr='gte')
    date_to = django_filters.IsoDateTimeFilter(field_name='date', lookup_expr='lte')
    price_min = django_filters.NumberFilter(
        field_name='sectors__price', lookup_expr='gte', distinct=True
    )
    price_max = django_filters.NumberFilter(
        field_name='sectors__price', lookup_expr='lte', distinct=True
    )

    class Meta:
        model = Event
        fields = ['venue', 'date_from', 'date_to', 'price_min', 'price_max']


class SectorFilter(django_filters.FilterSet):
    """Filtros de sectores/localidades."""

    event = django_filters.NumberFilter(field_name='event_id')
    price_min = django_filters.NumberFilter(field_name='price', lookup_expr='gte')
    price_max = django_filters.NumberFilter(field_name='price', lookup_expr='lte')
    available = django_filters.BooleanFilter(method='filter_available')

    class Meta:
        model = Sector
        fields = ['event', 'price_min', 'price_max', 'available']

    def filter_available(self, queryset, name, value):
        if value is True:
            return queryset.filter(available_stock__gt=0)
        if value is False:
            return queryset.filter(available_stock=0)
        return queryset
