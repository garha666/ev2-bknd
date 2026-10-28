from django.contrib.auth.models import User
from django.db import transaction
from django.http import JsonResponse
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import filters, generics, permissions, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView

from . import services
from .constants import ALUMNO
from .filters import EventFilter, SectorFilter
from .models import (
    Cart,
    CartItem,
    Event,
    Order,
    Sector,
    Ticket,
    Venue,
)
from .serializers import (
    CartItemAddSerializer,
    CartSerializer,
    CustomTokenObtainPairSerializer,
    EventSerializer,
    OrderSerializer,
    OrderStatusUpdateSerializer,
    SectorSerializer,
    StatusResponseSerializer,
    TicketSerializer,
    UserSerializer,
    VenueSerializer,
)


# 0. Vista Base de Verificación
@extend_schema(responses=StatusResponseSerializer, tags=['status'])
@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def api_status_view(request):
    """Endpoint de salud que expone la identificación del alumno."""
    return JsonResponse({
        "status": "OK",
        "sistema": "Plataforma de Boletaje para Eventos y Conciertos - Proyecto 3",
        "alumno": ALUMNO,
    }, status=status.HTTP_200_OK)


# 1. Permiso Personalizado para Roles
class IsOrganizadorOrReadOnly(permissions.BasePermission):
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return bool(request.user and request.user.is_authenticated and request.user.is_staff)


# 2. Autenticación JWT y Registro
class CustomTokenObtainPairView(TokenObtainPairView):
    # Spec 001: incluye claims de rol (Espectador / Organizador) en el token.
    serializer_class = CustomTokenObtainPairSerializer


class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [permissions.AllowAny]


# 3. ViewSets Principales
class VenueViewSet(viewsets.ModelViewSet):
    queryset = Venue.objects.all()
    serializer_class = VenueSerializer
    permission_classes = [IsOrganizadorOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'address', 'city']
    ordering_fields = ['id', 'name']


class EventViewSet(viewsets.ModelViewSet):
    queryset = Event.objects.select_related('venue').all()
    serializer_class = EventSerializer
    permission_classes = [IsOrganizadorOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = EventFilter
    search_fields = ['title', 'description']
    ordering_fields = ['date', 'title', 'id']

    @action(detail=True, methods=['get'])
    def sectores(self, request, pk=None):
        """Spec 001: GET /api/eventos/{id}/sectores/ — stock por sector."""
        event = self.get_object()
        sectors = event.sectors.all()
        return Response(SectorSerializer(sectors, many=True).data)


class SectorViewSet(viewsets.ModelViewSet):
    queryset = Sector.objects.select_related('event').all()
    serializer_class = SectorSerializer
    permission_classes = [IsOrganizadorOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = SectorFilter
    search_fields = ['name']
    ordering_fields = ['price', 'available_stock']


# 4. ViewSet para Carro de Compras (solo lectura + acciones)
class CartViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = CartSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if getattr(self, 'swagger_fake_view', False) or not user or user.is_anonymous:
            return Cart.objects.none()

        return Cart.objects.filter(user=user).prefetch_related('items__sector')

    @action(detail=False, methods=['get'])
    def my_cart(self, request):
        cart, _ = Cart.objects.prefetch_related('items__sector').get_or_create(user=request.user)
        serializer = self.get_serializer(cart)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'])
    @transaction.atomic
    def add_item(self, request):
        serializer = CartItemAddSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        sector_id = serializer.validated_data['sector_id']
        quantity = serializer.validated_data['quantity']

        cart, _ = Cart.objects.get_or_create(user=request.user)

        # 2.2 Bloqueo pesimista del sector para validar el stock acumulado
        # (existente en el carro + nuevo <= disponible) sin carreras.
        try:
            sector = Sector.objects.select_for_update().get(pk=sector_id)
        except Sector.DoesNotExist:
            raise ValidationError({'sector_id': 'El sector especificado no existe.'})

        existing_quantity = CartItem.objects.filter(
            cart=cart, sector=sector
        ).values_list('quantity', flat=True).first() or 0

        if existing_quantity + quantity > sector.available_stock:
            raise ValidationError(
                {'quantity': f'Stock insuficiente. Disponibles: {sector.available_stock}, ya en el carro: {existing_quantity}'}
            )

        cart_item, created = CartItem.objects.get_or_create(
            cart=cart,
            sector=sector,
            defaults={'quantity': quantity}
        )

        if not created:
            cart_item.quantity += quantity
            cart_item.save()

        return Response({'message': 'Entrada agregada al carro. El stock se confirmará al momento del pago.'}, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'])
    @transaction.atomic
    def remove_item(self, request):
        item_id = request.data.get('item_id')
        if not item_id:
            raise ValidationError({'item_id': 'El ID del ítem es requerido.'})

        try:
            item = CartItem.objects.get(id=item_id, cart__user=request.user)
            item.delete()
        except CartItem.DoesNotExist:
            return Response(
                {'error': 'No se encontró el ítem especificado en el carro.'},
                status=status.HTTP_404_NOT_FOUND
            )

        return Response({'message': 'Ítem eliminado del carro.'}, status=status.HTTP_200_OK)

    @transaction.atomic
    def destroy_item(self, request, pk=None):
        """Spec 001: DELETE /api/carro-tickets/{item_id}/."""
        item = CartItem.objects.filter(pk=pk, cart__user=request.user).first()
        if item is None:
            return Response(
                {'error': 'No se encontró el ítem especificado en el carro.'},
                status=status.HTTP_404_NOT_FOUND
            )
        item.delete()
        return Response({'message': 'Ítem eliminado del carro.'}, status=status.HTTP_200_OK)


# 5. ViewSet para Órdenes (solo lectura + acciones de negocio)
class OrderViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['status']
    ordering_fields = ['created_at', 'total_amount']

    def get_queryset(self):
        user = self.request.user
        if getattr(self, 'swagger_fake_view', False) or not user or user.is_anonymous:
            return Order.objects.none()

        base_qs = Order.objects.prefetch_related('items__sector')
        if user.is_staff:
            return base_qs.all()
        return base_qs.filter(user=user)

    # --- Helpers internos de negocio -------------------------------------

    def _create_order_from_cart(self, user):
        """Crea una orden PENDIENTE a partir del carro del usuario."""
        return services.create_order_from_cart(user)

    def _process_payment(self, order):
        """Descuenta stock, emite tickets y marca la orden como PAGADO.

        La transacción y el bloqueo pesimista viven en services.process_payment.
        """
        return services.process_payment(order)

    def _restore_stock(self, order):
        """Restituye stock y anula tickets de una orden pagada/entregada."""
        services.restore_stock(order)

    # --- Acciones de negocio ---------------------------------------------

    @action(detail=False, methods=['post'])
    @transaction.atomic
    def checkout(self, request):
        """Crea la orden PENDIENTE sin cobrar (flujo legacy)."""
        order = self._create_order_from_cart(request.user)
        return Response(self.get_serializer(order).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'])
    @transaction.atomic
    def pagar(self, request):
        """Spec 001: POST /api/compras/pagar/ — checkout + pago atómico."""
        order = self._create_order_from_cart(request.user)
        order = Order.objects.select_for_update().get(pk=order.pk)
        order = self._process_payment(order)
        return Response({
            'message': 'Pago procesado exitosamente. Entradas generadas y carro actualizado.',
            'order': self.get_serializer(order).data,
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def pay_order(self, request, pk=None):
        # 1.1 Bloqueo pesimista antes de verificar el estado.
        order = self.get_object()
        order = Order.objects.select_for_update().get(pk=order.pk)
        order = self._process_payment(order)
        return Response({
            'message': 'Pago procesado exitosamente. Entradas generadas y carro actualizado.',
            'order': self.get_serializer(order).data,
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def cancel_order(self, request, pk=None):
        # 1.4 El bloqueo y la reposición de stock viven en services.cancel_order.
        order = self.get_object()
        order = services.cancel_order(order)

        return Response({
            'message': 'Orden cancelada correctamente. Stock restituido.',
            'order': self.get_serializer(order).data,
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['patch'], url_path='estado')
    @transaction.atomic
    def estado(self, request, pk=None):
        """Spec 001: PATCH /api/compras/{id}/estado/ (solo Organizador)."""
        if not (request.user and request.user.is_authenticated and request.user.is_staff):
            raise PermissionDenied(
                'Solo un organizador puede cambiar el estado de una orden.'
            )

        serializer = OrderStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_status = serializer.validated_data['status']

        order = self.get_object()
        order = Order.objects.select_for_update().get(pk=order.pk)

        if order.status == new_status:
            return Response({
                'message': 'La orden ya se encuentra en ese estado.',
                'order': self.get_serializer(order).data,
            })

        order = services.change_order_status(order, new_status)

        return Response({
            'message': 'Estado actualizado.',
            'order': self.get_serializer(order).data,
        })


# 6. ViewSet para Tickets
class TicketViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = TicketSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['status']

    def get_queryset(self):
        user = self.request.user
        if getattr(self, 'swagger_fake_view', False) or not user or user.is_anonymous:
            return Ticket.objects.none()

        base_qs = Ticket.objects.select_related('order_item__order', 'sector', 'user')
        if user.is_staff:
            return base_qs.all()
        return base_qs.filter(user=user)