"""
Modelos de la Plataforma de Venta de Entradas para Eventos y Conciertos.

Esquema relacional:
    Venue (1) ──< Event (1) ──< Sector (1) ──< CartItem >── (1) Cart
                                              └──────────> OrderItem >── Order
                                                              └──< Ticket

Reglas de negocio relevantes:
    * Cart mantiene una relación 1:1 con el User (carro persistente).
    * Order usa CHOICES para el ciclo de vida de la transacción.
    * Sector.available_stock sólo se descuenta al pasar la orden a PAGADO.
    * Ticket se emite con un UUID único e irrepetible.
"""

import uuid

from django.contrib.auth.models import User
from django.db import models


# ============================================================================
# 1. Recinto o lugar donde se realiza el evento
# ============================================================================
class Venue(models.Model):
    """Recinto físico que alberga uno o más eventos."""

    name = models.CharField(max_length=150)
    address = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    capacity = models.PositiveIntegerField()

    def __str__(self):
        return f"{self.name} - {self.city}"


# ============================================================================
# 2. Evento / concierto
# ============================================================================
class Event(models.Model):
    """Evento publicado en el catálogo, asociado a un recinto."""

    title = models.CharField(max_length=200)
    description = models.TextField()
    date = models.DateTimeField()
    venue = models.ForeignKey(
        Venue,
        on_delete=models.CASCADE,
        related_name="events",
    )

    def __str__(self):
        return self.title


# ============================================================================
# 3. Sector / localidad con control de aforo y stock
# ============================================================================
class Sector(models.Model):
    """Localidad de un evento (Cancha General, VIP, Tribuna, etc.).

    `available_stock` es el stock vendible en tiempo real. No se modifica al
    agregar al carro; sólo se descuenta de forma atómica al confirmar el pago.
    """

    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name="sectors",
    )
    name = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=8, decimal_places=2)
    capacity = models.PositiveIntegerField()
    available_stock = models.PositiveIntegerField()

    def __str__(self):
        return f"{self.name} - {self.event.title} (${self.price})"


# ============================================================================
# 4. Carro de compras persistente (relación 1:1 con el usuario)
# ============================================================================
class Cart(models.Model):
    """Carro de compras persistente en PostgreSQL, uno por usuario."""

    STATUS = [
        ("ACTIVO", "Activo"),
        ("PROCESADO", "Procesado"),
    ]

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="cart",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=10, choices=STATUS, default="ACTIVO")

    def __str__(self):
        return f"Carro de {self.user.username} - {self.status}"


class CartItem(models.Model):
    """Ítem del carro: un sector y la cantidad solicitada.

    La restricción única evita duplicar el mismo sector dentro del carro.
    """

    cart = models.ForeignKey(
        Cart,
        on_delete=models.CASCADE,
        related_name="items",
    )
    sector = models.ForeignKey(Sector, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["cart", "sector"],
                name="unique_cart_item_per_sector",
            ),
        ]

    def __str__(self):
        return (
            f"{self.quantity} x {self.sector.name} "
            f"in {self.cart.user.username}'s cart"
        )

    @property
    def subtotal(self):
        """Valor de la línea (cantidad por precio unitario del sector)."""
        return self.quantity * self.sector.price


# ============================================================================
# 5. Orden de compra (control transaccional e histórico de precios)
# ============================================================================
class Order(models.Model):
    """Orden generada en el checkout.

    El campo `status` usa CHOICES y define el ciclo de vida de la transacción:
    PENDIENTE -> PAGADO -> ENTREGADO / CANCELADO.
    """

    STATUS = [
        ("PENDIENTE", "Pendiente"),
        ("PAGADO", "Pagado"),
        ("ENTREGADO", "Entregado"),
        ("CANCELADO", "Cancelado"),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="orders",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=10, choices=STATUS, default="PENDIENTE")
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Orden #{self.id} - {self.user.username} [{self.status}]"


class OrderItem(models.Model):
    """Detalle histórico de la orden.

    `unit_price` congela el precio del catálogo al momento del checkout para
    que cambios posteriores no alteren la venta ya realizada.
    """

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="items",
    )
    sector = models.ForeignKey(Sector, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=8, decimal_places=2)

    def __str__(self):
        return f"{self.quantity}x {self.sector.name} (Orden #{self.order.id})"

    @property
    def subtotal(self):
        """Valor histórico de la línea (cantidad por precio congelado)."""
        return self.quantity * self.unit_price


# ============================================================================
# 6. Entrada / ticket emitido con UUID único
# ============================================================================
class Ticket(models.Model):
    """Entrada individual emitida al confirmarse el pago.

    Cada ticket posee un `ticket_code` UUID irrepetible que sirve como código
    de acceso válido para el evento.
    """

    TICKET_STATUS = [
        ("VALIDO", "Válido"),
        ("USADO", "Usado"),
        ("ANULADO", "Anulado"),
    ]

    ticket_code = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    order_item = models.ForeignKey(
        OrderItem,
        on_delete=models.CASCADE,
        related_name="tickets",
    )
    sector = models.ForeignKey(Sector, on_delete=models.CASCADE)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="tickets",
    )
    issued_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(
        max_length=10,
        choices=TICKET_STATUS,
        default="VALIDO",
    )

    def __str__(self):
        return (
            f"Ticket {self.ticket_code} - "
            f"{self.sector.event.title} [{self.status}]"
        )
