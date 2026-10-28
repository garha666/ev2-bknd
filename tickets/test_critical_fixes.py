"""Tests de regresión para las correcciones críticas:

1.1 - pay_order bloquea la fila de la orden (sin doble pago concurrente)
1.2 - cancel_order bloquea la fila de la orden (sin doble cancelación)
1.3 - OrderViewSet es de solo lectura (sin bypass de negocio)
1.4 - CartViewSet es de solo lectura (sin manipular carros de otros)

Necesita TransactionTestCase porque usa hilos reales y select_for_update().
"""
from concurrent.futures import ThreadPoolExecutor

from django.contrib.auth.models import User
from django.db import close_old_connections
from django.test import TransactionTestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from .models import Cart, CartItem, Event, Order, Sector, Ticket, Venue


class BaseSetupMixin:
    """Datos base compartidos por los tests."""

    def setup_base(self):
        self.user1 = User.objects.create_user(username="user1", password="password123")
        self.user2 = User.objects.create_user(username="user2", password="password123")
        venue = Venue.objects.create(name="V", address="A", city="C", capacity=100)
        event = Event.objects.create(title="E", description="D", date="2026-12-01T20:00:00Z", venue=venue)
        self.sector = Sector.objects.create(event=event, name="VIP", price=10, capacity=100, available_stock=10)


class PayOrderConcurrencyTests(BaseSetupMixin, TransactionTestCase):
    """1.1: pago concurrente debe ser idempotente - un solo pago exitoso."""

    def setUp(self):
        self.setup_base()
        # user1 crea su orden PENDIENTE (1 entrada)
        client = APIClient()
        client.force_authenticate(user=self.user1)
        client.post(reverse("tickets:cart-add-item"), {"sector_id": self.sector.id, "quantity": 1}, format="json")
        resp = client.post(reverse("tickets:order-checkout"), {}, format="json")
        self.order_id = resp.data["id"]

    def _pay(self, username):
        close_old_connections()
        client = APIClient()
        client.force_authenticate(user=User.objects.get(username=username))
        resp = client.post(reverse("tickets:order-pay-order", kwargs={"pk": self.order_id}), {}, format="json")
        close_old_connections()
        return resp.status_code

    def test_concurrent_pay_only_one_success(self):
        """8 pagos simultáneos: exactamente 1 exitoso, 1 ticket, stock -1."""
        with ThreadPoolExecutor(max_workers=8) as executor:
            codes = list(executor.map(lambda _: self._pay("user1"), range(8)))

        self.sector.refresh_from_db()
        order = Order.objects.get(pk=self.order_id)

        self.assertEqual(codes.count(status.HTTP_200_OK), 1)
        self.assertEqual(codes.count(status.HTTP_400_BAD_REQUEST), 7)
        self.assertEqual(Ticket.objects.filter(order_item__order_id=self.order_id).count(), 1)
        self.assertEqual(self.sector.available_stock, 9)
        self.assertEqual(order.status, "PAGADO")

    def test_sequential_double_pay_rejected(self):
        """Pagar dos veces seguidas: la segunda debe rechazarse."""
        first = self._pay("user1")
        second = self._pay("user1")

        self.assertEqual(first, status.HTTP_200_OK)
        self.assertEqual(second, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Ticket.objects.filter(order_item__order_id=self.order_id).count(), 1)
        self.sector.refresh_from_db()
        self.assertEqual(self.sector.available_stock, 9)


class CancelOrderConcurrencyTests(BaseSetupMixin, TransactionTestCase):
    """1.2: cancelación concurrente debe restituir stock una sola vez."""

    def setUp(self):
        self.setup_base()
        client = APIClient()
        client.force_authenticate(user=self.user1)
        client.post(reverse("tickets:cart-add-item"), {"sector_id": self.sector.id, "quantity": 2}, format="json")
        resp = client.post(reverse("tickets:order-checkout"), {}, format="json")
        self.order_id = resp.data["id"]
        client.post(reverse("tickets:order-pay-order", kwargs={"pk": self.order_id}), {}, format="json")

    def _cancel(self, username):
        close_old_connections()
        client = APIClient()
        client.force_authenticate(user=User.objects.get(username=username))
        resp = client.post(reverse("tickets:order-cancel-order", kwargs={"pk": self.order_id}), {}, format="json")
        close_old_connections()
        return resp.status_code

    def test_concurrent_cancel_restores_stock_once(self):
        """5 cancelaciones simultáneas: una sola restitución de stock."""
        with ThreadPoolExecutor(max_workers=5) as executor:
            codes = list(executor.map(lambda _: self._cancel("user1"), range(5)))

        self.sector.refresh_from_db()
        order = Order.objects.get(pk=self.order_id)

        # stock: 10 -> 8 (pago) -> 10 (una única restitución)
        self.assertEqual(self.sector.available_stock, 10)
        self.assertEqual(codes.count(status.HTTP_200_OK), 1)
        self.assertEqual(order.status, "CANCELADO")
        self.assertEqual(Ticket.objects.filter(order_item__order_id=self.order_id, status="ANULADO").count(), 2)


class OrderViewSetReadOnlyTests(BaseSetupMixin, TransactionTestCase):
    """1.3: la orden solo se crea/actualiza/cancela por negocio, no por CRUD."""

    def setUp(self):
        self.setup_base()
        self.client = APIClient()
        self.client.force_authenticate(user=self.user1)

    def _make_paid_order(self):
        self.client.post(reverse("tickets:cart-add-item"), {"sector_id": self.sector.id, "quantity": 1}, format="json")
        resp = self.client.post(reverse("tickets:order-checkout"), {}, format="json")
        order_id = resp.data["id"]
        self.client.post(reverse("tickets:order-pay-order", kwargs={"pk": order_id}), {}, format="json")
        return order_id

    def test_cannot_create_order_directly(self):
        resp = self.client.post(reverse("tickets:order-list"), {
            "user": self.user2.id,
            "status": "PAGADO",
            "total_amount": "0.00",
        }, format="json")
        self.assertIn(resp.status_code, (status.HTTP_405_METHOD_NOT_ALLOWED, status.HTTP_403_FORBIDDEN))
        self.assertFalse(Order.objects.filter(user=self.user2).exists())

    def test_cannot_patch_order_status(self):
        order_id = self._make_paid_order()
        resp = self.client.patch(
            reverse("tickets:order-detail", kwargs={"pk": order_id}),
            {"status": "PENDIENTE"},
            format="json",
        )
        self.assertIn(resp.status_code, (status.HTTP_405_METHOD_NOT_ALLOWED, status.HTTP_403_FORBIDDEN))
        self.assertEqual(Order.objects.get(pk=order_id).status, "PAGADO")

    def test_cannot_delete_order(self):
        order_id = self._make_paid_order()
        resp = self.client.delete(reverse("tickets:order-detail", kwargs={"pk": order_id}))
        self.assertIn(resp.status_code, (status.HTTP_405_METHOD_NOT_ALLOWED, status.HTTP_403_FORBIDDEN))
        self.assertTrue(Order.objects.filter(pk=order_id).exists())
        self.assertEqual(Ticket.objects.filter(order_item__order_id=order_id).count(), 1)

    def test_reopened_order_cannot_pay_again(self):
        """Tras el fix no existe ruta para reabrir la orden; el pago doble se rechaza."""
        order_id = self._make_paid_order()
        second_pay = self.client.post(
            reverse("tickets:order-pay-order", kwargs={"pk": order_id}), {}, format="json"
        )
        self.assertEqual(second_pay.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Ticket.objects.filter(order_item__order_id=order_id).count(), 1)


class CartViewSetReadOnlyTests(BaseSetupMixin, TransactionTestCase):
    """1.4: el carro solo se manipula por sus acciones, no por CRUD directo."""

    def setUp(self):
        self.setup_base()
        self.client = APIClient()
        self.client.force_authenticate(user=self.user1)

    def test_cannot_create_cart_for_another_user(self):
        resp = self.client.post(reverse("tickets:cart-list"), {"user": self.user2.id}, format="json")
        self.assertIn(resp.status_code, (status.HTTP_405_METHOD_NOT_ALLOWED, status.HTTP_403_FORBIDDEN))
        self.assertFalse(Cart.objects.filter(user=self.user2).exists())

    def test_cannot_reassign_cart_user(self):
        cart, _ = Cart.objects.get_or_create(user=self.user1)
        resp = self.client.patch(reverse("tickets:cart-detail", kwargs={"pk": cart.pk}), {"user": self.user2.id}, format="json")
        self.assertIn(resp.status_code, (status.HTTP_405_METHOD_NOT_ALLOWED, status.HTTP_403_FORBIDDEN))
        cart.refresh_from_db()
        self.assertEqual(cart.user_id, self.user1.id)

    def test_cannot_delete_another_users_cart(self):
        cart2, _ = Cart.objects.get_or_create(user=self.user2)
        CartItem.objects.create(cart=cart2, sector=self.sector, quantity=1)
        resp = self.client.delete(reverse("tickets:cart-detail", kwargs={"pk": cart2.pk}))
        self.assertIn(resp.status_code, (status.HTTP_405_METHOD_NOT_ALLOWED, status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND))
        self.assertTrue(Cart.objects.filter(pk=cart2.pk).exists())
