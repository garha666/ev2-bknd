from django.contrib.auth.models import User
from django.db import transaction
from django.http import JsonResponse
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, generics, permissions, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView

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
from .serializers import (
    CartItemAddSerializer,
    CartSerializer,
    CustomTokenObtainPairSerializer,
    EventSerializer,
    OrderSerializer,
    SectorSerializer,
    TicketSerializer,
    UserSerializer,
    VenueSerializer,
)


# 0. Vista Base de Verificación
@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def api_status_view(request):
    return JsonResponse({
        "status": "OK",
        "sistema": "Plataforma de Boletaje para Eventos y Conciertos - Proyecto 3",
        "alumno": {
            "nombre_completo": "Matias Gubelin",
            "seccion": "IEC-N4-C1",
            "año": "2026"
        }
    }, status=status.HTTP_200_OK)


# 1. Permiso Personalizado para Roles
class IsOrganizadorOrReadOnly(permissions.BasePermission):
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return bool(request.user and request.user.is_authenticated and request.user.is_staff)


# 2. Autenticación JWT y Registro
class CustomTokenObtainPairView(TokenObtainPairView):
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
    filterset_fields = ['venue', 'date']
    search_fields = ['title', 'description']
    ordering_fields = ['date', 'title', 'id']


class SectorViewSet(viewsets.ModelViewSet):
    queryset = Sector.objects.select_related('event').all()
    serializer_class = SectorSerializer
    permission_classes = [IsOrganizadorOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['event']
    search_fields = ['name']
    ordering_fields = ['price', 'available_stock']


# 4. ViewSet para Carro de Compras
class CartViewSet(viewsets.ModelViewSet):
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
    def add_item(self, request):
        serializer = CartItemAddSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        sector_id = serializer.validated_data['sector_id']
        quantity = serializer.validated_data['quantity']

        try:
            sector = Sector.objects.get(pk=sector_id)
        except Sector.DoesNotExist:
            raise ValidationError({'sector_id': 'El sector especificado no existe.'})

        if quantity > sector.available_stock:
            raise ValidationError(
                {'quantity': f'Stock insuficiente. Disponibles: {sector.available_stock}'}
            )

        cart, _ = Cart.objects.get_or_create(user=request.user)

        cart_item, created = CartItem.objects.get_or_create(
            cart=cart,
            sector=sector,
            defaults={'quantity': quantity}
        )

        if not created:
            cart_item.quantity += quantity
            cart_item.save(update_fields=['quantity'])

        return Response({'message': 'Entrada agregada al carro con éxito.'}, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'])
    def remove_item(self, request):
        item_id = request.data.get('item_id')
        if not item_id:
            raise ValidationError({'item_id': 'El ID del ítem es requerido.'})

        deleted_count, _ = CartItem.objects.filter(
            cart__user=request.user,
            id=item_id
        ).delete()

        if deleted_count == 0:
            return Response(
                {'error': 'No se encontró el ítem especificado en el carro.'},
                status=status.HTTP_404_NOT_FOUND
            )

        return Response({'message': 'Ítem eliminado del carro.'}, status=status.HTTP_200_OK)


# 5. ViewSet para Órdenes
class OrderViewSet(viewsets.ModelViewSet):
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

    @action(detail=False, methods=['post'])
    @transaction.atomic
    def checkout(self, request):
        cart = Cart.objects.filter(user=request.user).prefetch_related('items__sector').first()

        if not cart or not cart.items.exists():
            raise ValidationError({'error': 'El carro de compras está vacío.'})

        cart_items = list(cart.items.all())
        total = sum(item.quantity * item.sector.price for item in cart_items)

        order = Order.objects.create(
            user=request.user,
            total_amount=total,
            status='PENDIENTE'
        )

        order_items = [
            OrderItem(
                order=order,
                sector=item.sector,
                quantity=item.quantity,
                unit_price=item.sector.price
            )
            for item in cart_items
        ]
        OrderItem.objects.bulk_create(order_items)

        cart.items.all().delete()

        serializer = self.get_serializer(order)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def pay_order(self, request, pk=None):
        order = self.get_object()

        if order.status != 'PENDIENTE':
            raise ValidationError({'error': f'No se puede pagar una orden en estado {order.status}.'})

        order_items = order.items.select_related('sector').all()
        sector_ids = [item.sector_id for item in order_items]

        sectors_db = {
            s.id: s for s in Sector.objects.filter(id__in=sector_ids).order_by('id').select_for_update()
        }

        for item in order_items:
            sector = sectors_db[item.sector_id]
            if item.quantity > sector.available_stock:
                raise ValidationError({
                    'error': f'Stock insuficiente para {sector.name}. Disponible: {sector.available_stock}, Solicitado: {item.quantity}'
                })

        tickets_to_create = []
        for item in order_items:
            sector = sectors_db[item.sector_id]
            sector.available_stock -= item.quantity
            sector.save(update_fields=['available_stock'])

            for _ in range(item.quantity):
                tickets_to_create.append(
                    Ticket(
                        order_item=item,
                        sector=sector,
                        user=order.user,
                        status='VALIDO'
                    )
                )

        Ticket.objects.bulk_create(tickets_to_create)

        order.status = 'COMPLETADA'
        order.save(update_fields=['status'])

        serializer = self.get_serializer(order)
        return Response({
            'message': 'Pago procesado exitosamente. Entradas generadas con éxito.',
            'order': serializer.data
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def cancel_order(self, request, pk=None):
        order = self.get_object()

        if order.status == 'CANCELADA':
            raise ValidationError({'error': 'La orden ya se encuentra cancelada.'})

        if order.status == 'COMPLETADA':
            order_items = order.items.select_related('sector').all()
            sector_ids = [item.sector_id for item in order_items]

            sectors_db = {
                s.id: s for s in Sector.objects.filter(id__in=sector_ids).order_by('id').select_for_update()
            }

            for item in order_items:
                sector = sectors_db[item.sector_id]
                sector.available_stock += item.quantity
                sector.save(update_fields=['available_stock'])

            Ticket.objects.filter(order_item__order=order).update(status='ANULADO')

        order.status = 'CANCELADA'
        order.save(update_fields=['status'])

        serializer = self.get_serializer(order)
        return Response({
            'message': 'Orden cancelada correctamente. Stock restituido.',
            'order': serializer.data
        }, status=status.HTTP_200_OK)


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