"""
Servicios de negocio compartidos entre la API (DRF) y las vistas HTML.

Concentrar aquí la lógica transaccional evita duplicar reglas críticas y
facilita la defensa oral: un único lugar define cómo se agrega al carro, cómo
se paga una orden, cómo se descuenta/repone stock y cómo se emiten tickets.
"""

from django.db import transaction
from django.db.models import F
from rest_framework.exceptions import ValidationError

from .models import Cart, CartItem, Order, OrderItem, Sector, Ticket


# ============================================================================
# Carro de compras
# ============================================================================
@transaction.atomic
def get_or_create_cart(user):
    """Devuelve el carro 1:1 del usuario, creándolo si no existe."""
    cart, _ = Cart.objects.get_or_create(user=user)
    return cart


@transaction.atomic
def add_item_to_cart(user, sector_id, quantity):
    """Agrega un sector al carro validando el stock acumulado.

    El stock NO se descuenta aquí: sólo se valida que lo solicitado (incluyendo
    lo que ya está en el carro) no supere el disponible. El descuento real
    ocurre al pagar.
    """
    try:
        quantity = int(quantity)
    except (TypeError, ValueError):
        raise ValidationError({'quantity': 'La cantidad debe ser un número entero.'})

    if quantity < 1:
        raise ValidationError({'quantity': 'La cantidad debe ser al menos 1.'})

    cart = get_or_create_cart(user)

    try:
        sector = Sector.objects.select_for_update().get(pk=sector_id)
    except (Sector.DoesNotExist, ValueError, TypeError):
        raise ValidationError({'sector_id': 'El sector especificado no existe.'})

    existing_quantity = (
        CartItem.objects.filter(cart=cart, sector=sector)
        .values_list('quantity', flat=True)
        .first()
        or 0
    )

    if existing_quantity + quantity > sector.available_stock:
        raise ValidationError({
            'quantity': (
                f'Stock insuficiente. Disponibles: {sector.available_stock}, '
                f'ya en el carro: {existing_quantity}'
            )
        })

    cart_item, created = CartItem.objects.get_or_create(
        cart=cart,
        sector=sector,
        defaults={'quantity': quantity},
    )

    if not created:
        cart_item.quantity += quantity
        cart_item.save(update_fields=['quantity'])

    return cart_item


@transaction.atomic
def remove_cart_item(user, item_id):
    """Elimina un ítem del carro del usuario autenticado."""
    item = CartItem.objects.filter(pk=item_id, cart__user=user).first()
    if item is None:
        raise ValidationError({
            'item_id': 'No se encontró el ítem especificado en el carro.'
        })
    item.delete()
    return True


# ============================================================================
# Checkout y pago
# ============================================================================
@transaction.atomic
def create_order_from_cart(user):
    """Convierte el carro activo en una orden PENDIENTE.

    Congela el precio unitario de cada sector en OrderItem para que cambios
    posteriores del catálogo no alteren la venta. El carro pasa a PROCESADO.
    """
    cart = (
        Cart.objects.filter(user=user)
        .prefetch_related('items__sector')
        .first()
    )

    if not cart or not cart.items.exists():
        raise ValidationError({'error': 'El carro de compras está vacío.'})

    cart_items = list(cart.items.all())
    total = sum(item.quantity * item.sector.price for item in cart_items)

    order = Order.objects.create(
        user=user,
        total_amount=total,
        status='PENDIENTE',
    )

    OrderItem.objects.bulk_create([
        OrderItem(
            order=order,
            sector=item.sector,
            quantity=item.quantity,
            unit_price=item.sector.price,
        )
        for item in cart_items
    ])

    cart.status = 'PROCESADO'
    cart.save(update_fields=['status'])
    return order


@transaction.atomic
def process_payment(order):
    """Paga una orden PENDIENTE de forma atómica.

    Pasos:
        1. Bloquea la orden (select_for_update) para evitar dobles pagos.
        2. Descuenta stock con una actualización condicional por sector.
        3. Emite un Ticket con UUID por cada unidad comprada.
        4. Marca la orden como PAGADO.
        5. Descuenta del carro las cantidades exactas del snapshot.
    """
    order = Order.objects.select_for_update().get(pk=order.pk)

    if order.status != 'PENDIENTE':
        raise ValidationError({
            'error': f'No se puede pagar una orden en estado {order.status}.'
        })

    order_items = list(order.items.select_related('sector').all())

    # 1. Descuento atómico condicionado al stock disponible.
    for item in order_items:
        updated_count = Sector.objects.filter(
            pk=item.sector_id,
            available_stock__gte=item.quantity,
        ).update(available_stock=F('available_stock') - item.quantity)

        if updated_count == 0:
            raise ValidationError({
                'error': (
                    f'Stock insuficiente para {item.sector.name}. '
                    'Alguien más acaba de comprar las últimas entradas.'
                )
            })

    # 2. Emisión de entradas con UUID único.
    Ticket.objects.bulk_create([
        Ticket(
            order_item=item,
            sector=item.sector,
            user=order.user,
            status='VALIDO',
        )
        for item in order_items
        for _ in range(item.quantity)
    ])

    # 3. Estado PAGADO.
    order.status = 'PAGADO'
    order.save(update_fields=['status'])

    # 4. Descuento del carro según el snapshot de la orden.
    for item in order_items:
        cart_item = CartItem.objects.filter(
            cart__user=order.user,
            sector_id=item.sector_id,
        ).first()

        if cart_item is None:
            continue

        if cart_item.quantity <= item.quantity:
            cart_item.delete()
        else:
            cart_item.quantity -= item.quantity
            cart_item.save(update_fields=['quantity'])

    return order


@transaction.atomic
def restore_stock(order):
    """Restituye el stock y anula los tickets de una orden pagada/entregada."""
    order_items = list(order.items.select_related('sector').all())
    sector_ids = [item.sector_id for item in order_items]

    sectors_db = {
        sector.id: sector
        for sector in (
            Sector.objects.filter(id__in=sector_ids)
            .order_by('id')
            .select_for_update()
        )
    }

    for item in order_items:
        sector = sectors_db[item.sector_id]
        sector.available_stock += item.quantity
        sector.save(update_fields=['available_stock'])

    Ticket.objects.filter(order_item__order=order).update(status='ANULADO')


@transaction.atomic
def cancel_order(order):
    """Cancela una orden y repone stock si ya estaba pagada/entregada."""
    order = Order.objects.select_for_update().get(pk=order.pk)

    if order.status == 'CANCELADO':
        raise ValidationError({'error': 'La orden ya se encuentra cancelada.'})

    if order.status in ('PAGADO', 'ENTREGADO'):
        restore_stock(order)

    order.status = 'CANCELADO'
    order.save(update_fields=['status'])
    return order


@transaction.atomic
def change_order_status(order, new_status):
    """Cambia el estado de una orden respetando las transiciones válidas."""
    order = Order.objects.select_for_update().get(pk=order.pk)

    if order.status == new_status:
        return order

    if order.status == 'CANCELADO':
        raise ValidationError({
            'error': 'Una orden cancelada no puede cambiar de estado.'
        })

    if new_status == 'PENDIENTE':
        raise ValidationError({'error': 'No se puede volver a PENDIENTE.'})

    if new_status == 'PAGADO':
        return process_payment(order)

    if new_status == 'ENTREGADO':
        if order.status != 'PAGADO':
            raise ValidationError({
                'error': f'No se puede pasar de {order.status} a ENTREGADO.'
            })
        order.status = 'ENTREGADO'
        order.save(update_fields=['status'])
        return order

    if new_status == 'CANCELADO':
        if order.status in ('PAGADO', 'ENTREGADO'):
            restore_stock(order)
        order.status = 'CANCELADO'
        order.save(update_fields=['status'])
        return order

    raise ValidationError({'status': 'Estado no válido.'})
