"""
Vistas HTML (server-rendered) de la plataforma.

La API REST sigue usando JWT; estas vistas usan la sesión de Django para que la
experiencia web sea simple (formularios + redirects). Toda la lógica crítica se
delega en `tickets.services` para no duplicar reglas de negocio.
"""

from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Count, Min, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from rest_framework.exceptions import ValidationError as DRFValidationError

from . import services
from .forms import (
    AddToCartForm,
    EventForm,
    LoginForm,
    OrderStatusForm,
    RegisterForm,
    SectorForm,
)
from .models import Cart, Event, Order, Ticket, Venue


# ============================================================================
# Utilidades
# ============================================================================
def _flatten_errors(exc):
    """Convierte los errores de DRF en un texto legible para messages."""
    detail = getattr(exc, 'detail', None)

    if isinstance(detail, dict):
        parts = []
        for field, errors in detail.items():
            if isinstance(errors, (list, tuple)):
                errors = ' '.join(str(error) for error in errors)
            parts.append(str(errors) if field == 'error' else f'{field}: {errors}')
        return ' '.join(parts)

    if isinstance(detail, (list, tuple)):
        return ' '.join(str(error) for error in detail)

    return str(detail or exc)


def _redirect_next(request, fallback):
    """Redirige a ?next= sólo si es una URL local segura."""
    next_url = request.GET.get('next') or request.POST.get('next')
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(next_url)
    return redirect(fallback)


# ============================================================================
# Catálogo público
# ============================================================================
def home(request):
    """Catálogo de eventos con búsqueda y filtros por recinto/precio."""
    events = Event.objects.select_related('venue').prefetch_related('sectors')

    query = request.GET.get('q', '').strip()
    venue_id = request.GET.get('venue', '').strip()
    price_min = request.GET.get('price_min', '').strip()
    price_max = request.GET.get('price_max', '').strip()

    if query:
        events = events.filter(
            Q(title__icontains=query)
            | Q(description__icontains=query)
            | Q(venue__name__icontains=query)
        )

    if venue_id.isdigit():
        events = events.filter(venue_id=venue_id)

    if price_min:
        events = events.filter(sectors__price__gte=price_min)

    if price_max:
        events = events.filter(sectors__price__lte=price_max)

    events = events.annotate(
        min_price=Min('sectors__price'),
        sector_count=Count('sectors', distinct=True),
        total_stock=Sum('sectors__available_stock'),
    ).distinct().order_by('date')

    return render(request, 'tickets/home.html', {
        'events': events,
        'venues': Venue.objects.order_by('name'),
        'filters': {
            'q': query,
            'venue': venue_id,
            'price_min': price_min,
            'price_max': price_max,
        },
    })


def event_detail(request, pk):
    """Detalle de un evento con sus sectores y stock disponible."""
    event = get_object_or_404(
        Event.objects.select_related('venue').prefetch_related('sectors'),
        pk=pk,
    )
    return render(request, 'tickets/event_detail.html', {
        'event': event,
        'sectors': event.sectors.order_by('price'),
        'form': AddToCartForm(),
    })


# ============================================================================
# Carro persistente
# ============================================================================
@login_required
def cart_detail(request):
    cart = services.get_or_create_cart(request.user)
    cart = (
        Cart.objects.prefetch_related('items__sector__event')
        .get(pk=cart.pk)
    )
    items = list(cart.items.all())
    total = sum(item.quantity * item.sector.price for item in items)

    return render(request, 'tickets/cart.html', {
        'cart': cart,
        'items': items,
        'total': total,
    })


@login_required
@require_POST
def add_to_cart(request, sector_id):
    form = AddToCartForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'La cantidad ingresada no es válida.')
        event_id = request.POST.get('event_id')
        if event_id:
            return redirect('web:event_detail', pk=event_id)
        return redirect('web:home')

    try:
        services.add_item_to_cart(
            request.user,
            sector_id,
            form.cleaned_data['quantity'],
        )
        messages.success(
            request,
            'Entrada agregada al carro. El stock se confirmará al pagar.',
        )
    except DRFValidationError as exc:
        messages.error(request, _flatten_errors(exc))

    event_id = request.POST.get('event_id')
    if event_id:
        return redirect('web:event_detail', pk=event_id)
    return redirect('web:cart_detail')


@login_required
@require_POST
def remove_from_cart(request, item_id):
    try:
        services.remove_cart_item(request.user, item_id)
        messages.success(request, 'Ítem eliminado del carro.')
    except DRFValidationError as exc:
        messages.error(request, _flatten_errors(exc))
    return redirect('web:cart_detail')


# ============================================================================
# Checkout, pago y órdenes
# ============================================================================
@login_required
@require_POST
def checkout(request):
    try:
        order = services.create_order_from_cart(request.user)
        messages.success(
            request,
            f'Orden #{order.id} generada en estado PENDIENTE. Ahora puedes pagarla.',
        )
    except DRFValidationError as exc:
        messages.error(request, _flatten_errors(exc))
        return redirect('web:cart_detail')

    return redirect('web:my_orders')


@login_required
def my_orders(request):
    orders = (
        Order.objects.filter(user=request.user)
        .prefetch_related('items__sector__event')
        .order_by('-created_at')
    )
    return render(request, 'tickets/orders.html', {'orders': orders})


@login_required
@require_POST
def pay_order(request, pk):
    order = get_object_or_404(Order, pk=pk, user=request.user)
    try:
        services.process_payment(order)
        messages.success(
            request,
            'Pago procesado. Tus entradas fueron emitidas con su código UUID.',
        )
    except DRFValidationError as exc:
        messages.error(request, _flatten_errors(exc))
    return redirect('web:my_orders')


@login_required
@require_POST
def cancel_order(request, pk):
    order = get_object_or_404(Order, pk=pk, user=request.user)
    try:
        services.cancel_order(order)
        messages.success(request, 'Orden cancelada. El stock fue restituido.')
    except DRFValidationError as exc:
        messages.error(request, _flatten_errors(exc))
    return redirect('web:my_orders')


@login_required
def my_tickets(request):
    tickets = (
        Ticket.objects.filter(user=request.user)
        .select_related('sector__event', 'order_item__order')
        .order_by('-issued_at')
    )
    return render(request, 'tickets/tickets.html', {'tickets': tickets})


# ============================================================================
# Autenticación por sesión (para la web)
# ============================================================================
def login_view(request):
    if request.user.is_authenticated:
        return _redirect_next(request, 'web:home')

    form = LoginForm(request, data=request.POST or None)

    if request.method == 'POST' and form.is_valid():
        auth_login(request, form.get_user())
        messages.success(request, f'Bienvenido, {form.get_user().username}.')
        return _redirect_next(request, 'web:home')

    return render(request, 'tickets/login.html', {'form': form})


def logout_view(request):
    auth_logout(request)
    messages.info(request, 'Sesión cerrada correctamente.')
    return redirect('web:home')


def register_view(request):
    if request.user.is_authenticated:
        return redirect('web:home')

    form = RegisterForm(request.POST or None)

    if request.method == 'POST' and form.is_valid():
        user = form.save()
        auth_login(request, user)
        messages.success(request, 'Cuenta creada. ¡Ya puedes comprar entradas!')
        return redirect('web:home')

    return render(request, 'tickets/register.html', {'form': form})


# ============================================================================
# Panel del organizador (staff)
# ============================================================================
def _is_staff(user):
    return bool(user.is_authenticated and user.is_staff)


@user_passes_test(_is_staff, login_url='web:login')
def panel(request):
    events = (
        Event.objects.select_related('venue')
        .prefetch_related('sectors')
        .order_by('-date')
    )
    orders = (
        Order.objects.select_related('user')
        .prefetch_related('items__sector__event')
        .order_by('-created_at')
    )
    orders_with_forms = [
        (order, OrderStatusForm(initial={'status': order.status}))
        for order in orders
    ]

    return render(request, 'tickets/panel.html', {
        'events': events,
        'orders_with_forms': orders_with_forms,
        'event_form': EventForm(),
        'sector_form': SectorForm(),
    })


@user_passes_test(_is_staff, login_url='web:login')
@require_POST
def panel_order_status(request, pk):
    order = get_object_or_404(Order, pk=pk)
    form = OrderStatusForm(request.POST)

    if not form.is_valid():
        messages.error(request, 'Estado inválido.')
        return redirect('web:panel')

    try:
        services.change_order_status(order, form.cleaned_data['status'])
        messages.success(request, f'Orden #{order.id} actualizada.')
    except DRFValidationError as exc:
        messages.error(request, _flatten_errors(exc))

    return redirect('web:panel')


@user_passes_test(_is_staff, login_url='web:login')
@require_POST
def panel_event_create(request):
    form = EventForm(request.POST)
    if form.is_valid():
        event = form.save()
        messages.success(request, f'Evento "{event.title}" creado.')
    else:
        messages.error(request, f'No se pudo crear el evento: {form.errors.as_text()}')
    return redirect('web:panel')


@user_passes_test(_is_staff, login_url='web:login')
@require_POST
def panel_sector_create(request):
    form = SectorForm(request.POST)
    if form.is_valid():
        sector = form.save()
        messages.success(request, f'Sector "{sector.name}" creado.')
    else:
        messages.error(request, f'No se pudo crear el sector: {form.errors.as_text()}')
    return redirect('web:panel')
