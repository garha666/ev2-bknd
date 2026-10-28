"""
Serializadores de la API de Venta de Entradas.

Incluye:
    * Serializadores de catálogo (Venue, Event, Sector).
    * Serializadores del carro persistente y de la orden.
    * Serializador de ticket con UUID.
    * CustomTokenObtainPairSerializer con claims de rol (Espectador/Organizador).
"""

from django.contrib.auth.models import User
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import (
    Cart,
    CartItem,
    Event,
    Order,
    OrderItem,
    Sector,
    Ticket,
    Venue,
)


# ============================================================================
# Usuarios y autenticación
# ============================================================================
class UserSerializer(serializers.ModelSerializer):
    """Registro de usuarios con hash de contraseña mediante create_user()."""

    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'password']

    def create(self, validated_data):
        # Se utiliza create_user para que Django aplique el hash seguro.
        return User.objects.create_user(
            username=validated_data['username'],
            email=validated_data.get('email', ''),
            password=validated_data['password'],
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', ''),
        )


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """JWT con claims de rol exigidos por el Spec 001."""

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['username'] = user.username
        token['is_staff'] = user.is_staff
        token['role'] = 'Organizador' if user.is_staff else 'Espectador'
        return token


# ============================================================================
# Catálogo: recintos, eventos y sectores
# ============================================================================
class VenueSerializer(serializers.ModelSerializer):
    class Meta:
        model = Venue
        fields = '__all__'


class EventSerializer(serializers.ModelSerializer):
    venue_name = serializers.ReadOnlyField(source='venue.name')

    class Meta:
        model = Event
        fields = ['id', 'title', 'description', 'date', 'venue', 'venue_name']


class SectorSerializer(serializers.ModelSerializer):
    event_name = serializers.ReadOnlyField(source='event.title')

    class Meta:
        model = Sector
        fields = [
            'id',
            'name',
            'price',
            'capacity',
            'available_stock',
            'event',
            'event_name',
        ]


# ============================================================================
# Carro persistente
# ============================================================================
class CartItemSerializer(serializers.ModelSerializer):
    sector_name = serializers.ReadOnlyField(source='sector.name')
    sector_price = serializers.ReadOnlyField(source='sector.price')

    class Meta:
        model = CartItem
        fields = ['id', 'sector', 'sector_name', 'sector_price', 'quantity']


class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True)
    user_name = serializers.ReadOnlyField(source='user.username')

    class Meta:
        model = Cart
        fields = ['id', 'user', 'user_name', 'created_at', 'status', 'items']
        read_only_fields = ['user', 'created_at', 'status']


class CartItemAddSerializer(serializers.Serializer):
    """Payload para agregar un sector al carro."""

    sector_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1)


# ============================================================================
# Órdenes y tickets
# ============================================================================
class OrderItemSerializer(serializers.ModelSerializer):
    sector_name = serializers.ReadOnlyField(source='sector.name')

    class Meta:
        model = OrderItem
        fields = ['id', 'sector', 'sector_name', 'quantity', 'unit_price']


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    user_name = serializers.ReadOnlyField(source='user.username')

    class Meta:
        model = Order
        fields = [
            'id',
            'user',
            'user_name',
            'created_at',
            'status',
            'total_amount',
            'items',
            'updated_at',
        ]
        read_only_fields = ['user', 'status', 'total_amount', 'created_at', 'updated_at']


class OrderStatusUpdateSerializer(serializers.Serializer):
    """Validación del PATCH /api/compras/{id}/estado/ (Spec 001)."""

    status = serializers.ChoiceField(choices=[choice[0] for choice in Order.STATUS])


class TicketSerializer(serializers.ModelSerializer):
    event_title = serializers.ReadOnlyField(source='sector.event.title')
    sector_name = serializers.ReadOnlyField(source='sector.name')

    class Meta:
        model = Ticket
        fields = [
            'id',
            'ticket_code',
            'order_item',
            'sector',
            'sector_name',
            'user',
            'issued_at',
            'status',
            'event_title',
        ]


# ============================================================================
# Respuesta del endpoint de estado (/api/status/)
# ============================================================================
class StatusAlumnoSerializer(serializers.Serializer):
    nombre_completo = serializers.CharField()
    seccion = serializers.CharField()
    año = serializers.CharField()


class StatusResponseSerializer(serializers.Serializer):
    status = serializers.CharField()
    sistema = serializers.CharField()
    alumno = StatusAlumnoSerializer()
