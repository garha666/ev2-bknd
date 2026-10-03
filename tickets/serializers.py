from decimal import Decimal
from django.contrib.auth.models import User
from django.db import transaction
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import Cart, CartItem, Event, Order, OrderItem, Sector, Ticket, Venue


# 1. JWT Token Custom Serializer
class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['username'] = user.username
        token['email'] = user.email
        token['first_name'] = user.first_name
        token['last_name'] = user.last_name
        token['is_staff'] = user.is_staff
        token['role'] = 'Organizador' if user.is_staff else 'Espectador'
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        data['user'] = {
            'id': self.user.id,
            'username': self.user.username,
            'email': self.user.email,
            'first_name': self.user.first_name,
            'last_name': self.user.last_name,
            'is_staff': self.user.is_staff,
            'role': 'Organizador' if self.user.is_staff else 'Espectador',
        }
        return data


# 2. Registro de Usuarios
class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        write_only=True,
        required=True,
        style={'input_type': 'password'},
        min_length=8
    )

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'password', 'first_name', 'last_name', 'is_staff']
        read_only_fields = ['id']
        extra_kwargs = {
            'email': {'required': True},
            'is_staff': {'read_only': True}
        }

    @transaction.atomic
    def create(self, validated_data):
        validated_data.pop('is_staff', None)
        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data['email'],
            password=validated_data['password'],
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', '')
        )
        Cart.objects.create(user=user)
        return user


UserRegistrationSerializer = UserSerializer


# 3. Recintos, Eventos y Sectores
class VenueSerializer(serializers.ModelSerializer):
    class Meta:
        model = Venue
        fields = '__all__'


class SectorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Sector
        fields = '__all__'


class EventSerializer(serializers.ModelSerializer):
    venue_name = serializers.CharField(source='venue.name', read_only=True)

    class Meta:
        model = Event
        fields = '__all__'


# 4. Cart DTO
class CartItemAddSerializer(serializers.Serializer):
    sector_id = serializers.IntegerField(min_value=1, required=True)
    quantity = serializers.IntegerField(min_value=1, default=1)


# 5. Carrito de Compras
class CartItemSerializer(serializers.ModelSerializer):
    sector_name = serializers.CharField(source='sector.name', read_only=True)
    event_title = serializers.CharField(source='sector.event.title', read_only=True)
    unit_price = serializers.DecimalField(
        source='sector.price', max_digits=10, decimal_places=2, read_only=True
    )
    subtotal = serializers.SerializerMethodField()

    class Meta:
        model = CartItem
        fields = ['id', 'cart', 'sector', 'sector_name', 'event_title', 'quantity', 'unit_price', 'subtotal']
        read_only_fields = ['cart']

    @extend_schema_field(serializers.DecimalField(max_digits=10, decimal_places=2))
    def get_subtotal(self, obj) -> Decimal:
        if obj.sector and obj.sector.price is not None:
            return Decimal(obj.quantity) * obj.sector.price
        return Decimal('0.00')


class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True)
    total = serializers.SerializerMethodField()

    class Meta:
        model = Cart
        fields = ['id', 'user', 'status', 'created_at', 'items', 'total']
        read_only_fields = ['user', 'created_at']

    @extend_schema_field(serializers.DecimalField(max_digits=10, decimal_places=2))
    def get_total(self, obj) -> Decimal:
        return sum(
            (Decimal(item.quantity) * item.sector.price for item in obj.items.all() if item.sector and item.sector.price),
            Decimal('0.00')
        )


# 6. Órdenes y Tickets
class TicketSerializer(serializers.ModelSerializer):
    event_title = serializers.CharField(source='sector.event.title', read_only=True)
    sector_name = serializers.CharField(source='sector.name', read_only=True)
    order_id = serializers.IntegerField(source='order_item.order.id', read_only=True)

    class Meta:
        model = Ticket
        fields = ['id', 'ticket_code', 'order_item', 'order_id', 'sector', 'user', 'status', 'event_title', 'sector_name', 'issued_at']
        read_only_fields = ['id', 'ticket_code', 'issued_at', 'user']


class OrderItemSerializer(serializers.ModelSerializer):
    sector_name = serializers.CharField(source='sector.name', read_only=True)

    class Meta:
        model = OrderItem
        fields = ['id', 'order', 'sector', 'sector_name', 'quantity', 'unit_price']
        read_only_fields = ['order', 'unit_price']


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    tickets = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = ['id', 'user', 'created_at', 'status', 'total_amount', 'items', 'tickets', 'updated_at']
        read_only_fields = ['user', 'total_amount', 'created_at', 'status', 'updated_at']

    @extend_schema_field(TicketSerializer(many=True))
    def get_tickets(self, obj):
        tickets = Ticket.objects.filter(order_item__order=obj)
        return TicketSerializer(tickets, many=True).data