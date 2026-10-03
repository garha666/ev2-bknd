from django.db import models
import uuid
from django.db import models
from django.contrib.auth.models import User

# Create your models here.

# 1. Recinto o Lugar del Evento
class Venue(models.Model):
    name = models.CharField(max_length=150)
    address = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    capacity = models.PositiveIntegerField()

    def __str__(self):
        return f"{self.name} - {self.city}"

# 2. Evento  Concierto
class Event(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField()
    date = models.DateTimeField()
    venue = models.ForeignKey(Venue, on_delete=models.CASCADE, related_name='events')

    def __str__(self):
        return self.title

# 3. Sector  Localidad con Control de Aforo y Stock
class Sector(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='sectors')
    name = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=8, decimal_places=2)
    capacity = models.PositiveIntegerField()
    available_stock = models.PositiveIntegerField()

    def __str__(self):
        return f"{self.name} - {self.event.title} (${self.price})"

# 4. Carro de Compras Persistente (Relación 1:1 con el Usuario)
class Cart(models.Model):
    STATUS = [
        ('ACTIVO', 'Activo'),
        ('PROCESADO', 'Procesado'),
    ]
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='cart')
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=10, choices=STATUS, default='ACTIVO')

    def __str__(self):
        return f"Carro de {self.user.username} - {self.status}"

class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='items')
    sector = models.ForeignKey(Sector, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()

    def __str__(self):
        return f"{self.quantity} x {self.sector.name} in {self.cart.user.username}'s cart"

  # 5. Orden de Compra (Control Transaccional)
class Order(models.Model):
    STATUS = [
        ('PENDIENTE', 'Pendiente'),
        ('COMPLETADA', 'Completada'),
        ('CANCELADA', 'Cancelada'),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='orders')
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=10, choices=STATUS, default='PENDIENTE')
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Orden #{self.id} - {self.user.username} [{self.status}]"

class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    sector = models.ForeignKey(Sector, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=8, decimal_places=2)

    def __str__(self):
        return f"{self.quantity}x {self.sector.name} (Orden #{self.order.id})"

# 6. Entrada  Ticket Emitido con UUID Único
class Ticket(models.Model):
    TICKET_STATUS = [
        ('VALIDO', 'Válido'),
        ('USADO', 'Usado'),
        ('ANULADO', 'Anulado'),
    ]
    ticket_code = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    order_item = models.ForeignKey(OrderItem, on_delete=models.CASCADE, related_name='tickets')
    sector = models.ForeignKey(Sector, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='tickets')
    issued_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=10, choices=TICKET_STATUS, default='VALIDO')

    def __str__(self):
        return f"Ticket {self.ticket_code} - {self.sector.event.title} [{self.status}]"
    