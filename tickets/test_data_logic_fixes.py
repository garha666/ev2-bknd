"""Tests para las correcciones de lógica de datos:

2.1 - checkout marca Cart.status='PROCESADO' y pay_order descuenta del carro
      las cantidades exactas del snapshot de la orden.
2.2 - add_item valida stock acumulado (existente + nuevo <= disponible) y
      CartItem tiene UniqueConstraint(cart, sector).
2.3 - reserved_at eliminado de CartItem y del serializer.
"""
from django.contrib.auth.models import User
from django.db import models as dj_models
from django.db import connection
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from .models import Cart, CartItem, Event, Order, Sector, Ticket, Venue


class BaseCheckoutSetupMixin:
    def setup_base(self):
        self.user1 = User.objects.create_user(username="user1", password="password123")
        venue = Venue.objects.create(name="V", address="A", city="C", capacity=100)
        event = Event.objects.create(title="E", description="D", date="2026-12-01T20:00:00Z", venue=venue)
        self.sector = Sector.objects.create(event=event, name="VIP", price=10, capacity=100, available_stock=10)
        self.client = APIClient()
        self.client.force_authenticate(user=self.user1)

    def add_item(self, quantity, sector=None):
        return self.client.post(
            reverse("tickets:cart-add-item"),
            {"sector_id": (sector or self.sector).id, "quantity": quantity},
            format="json",
        )

    def checkout(self):
        return self.client.post(reverse("tickets:order-checkout"), {}, format="json")


class CheckoutCartStatusTests(BaseCheckoutSetupMixin, TestCase):
    """2.1a: el checkout marca el carro como PROCESADO."""

    def setUp(self):
        self.setup_base()

    def test_checkout_marks_cart_procesado(self):
        self.add_item(2)
        cart = Cart.objects.get(user=self.user1)
        self.assertEqual(cart.status, "ACTIVO")

        resp = self.checkout()
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        cart.refresh_from_db()
        self.assertEqual(cart.status, "PROCESADO")


class PayOrderCartSnapshotTests(BaseCheckoutSetupMixin, TestCase):
    """2.1b: pay_order descuenta del carro las cantidades exactas de la orden."""

    def setUp(self):
        self.setup_base()

    def _checkout_and_pay(self):
        resp = self.checkout()
        order_id = resp.data["id"]
        pay = self.client.post(reverse("tickets:order-pay-order", kwargs={"pk": order_id}), {}, format="json")
        self.assertEqual(pay.status_code, status.HTTP_200_OK)
        return order_id

    def test_pay_deletes_cart_item_when_quantity_matches(self):
        self.add_item(2)
        self._checkout_and_pay()

        self.assertFalse(CartItem.objects.filter(cart__user=self.user1).exists())

    def test_pay_decrements_exact_quantity_from_cart(self):
        """2 entradas en la orden + 3 agregadas después del checkout.
        Al pagar, el carro debe conservar solo las 3 nuevas."""
        self.add_item(2)
        resp = self.checkout()
        order_id = resp.data["id"]

        # El usuario agrega más del mismo sector DESPUÉS del checkout
        self.add_item(3)
        cart_item = CartItem.objects.get(cart__user=self.user1, sector=self.sector)
        self.assertEqual(cart_item.quantity, 5)

        pay = self.client.post(reverse("tickets:order-pay-order", kwargs={"pk": order_id}), {}, format="json")
        self.assertEqual(pay.status_code, status.HTTP_200_OK)

        cart_item.refresh_from_db()
        self.assertEqual(cart_item.quantity, 3)
        self.assertEqual(Ticket.objects.count(), 2)

        # Una segunda compra agotaría el resto
        self.sector.refresh_from_db()
        self.assertEqual(self.sector.available_stock, 8)

    def test_pay_leaves_items_of_other_sectors_intact(self):
        sector2 = Sector.objects.create(event=self.sector.event, name="General", price=5, capacity=100, available_stock=10)
        self.add_item(2, sector=self.sector)
        resp = self.checkout()
        order_id = resp.data["id"]

        # Ítem nuevo de otro sector agregado después del checkout
        self.add_item(4, sector=sector2)

        pay = self.client.post(reverse("tickets:order-pay-order", kwargs={"pk": order_id}), {}, format="json")
        self.assertEqual(pay.status_code, status.HTTP_200_OK)

        self.assertFalse(CartItem.objects.filter(cart__user=self.user1, sector=self.sector).exists())
        self.assertEqual(CartItem.objects.get(cart__user=self.user1, sector=sector2).quantity, 4)

    def test_multiple_checkouts_create_independent_orders(self):
        self.add_item(2)
        first = self.checkout()
        self.add_item(1)
        second = self.checkout()

        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Order.objects.filter(user=self.user1).count(), 2)


class AddItemStockValidationTests(BaseCheckoutSetupMixin, TestCase):
    """2.2: el stock acumulado del carro no puede exceder el disponible."""

    def setUp(self):
        self.setup_base()

    def test_rejects_when_accumulated_exceeds_stock(self):
        self.add_item(6)
        self.assertEqual(CartItem.objects.get(cart__user=self.user1).quantity, 6)

        resp = self.add_item(6)  # 6 + 6 > 10
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Stock insuficiente", str(resp.data))

        cart_item = CartItem.objects.get(cart__user=self.user1)
        cart_item.refresh_from_db()
        self.assertEqual(cart_item.quantity, 6)  # sin cambios

    def test_allows_accumulating_up_to_stock_limit(self):
        self.add_item(6)
        resp = self.add_item(4)  # 6 + 4 == 10
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(CartItem.objects.get(cart__user=self.user1).quantity, 10)

    def test_unique_constraint_cart_sector(self):
        """CartItem tiene UniqueConstraint(cart, sector) a nivel de modelo."""
        constraints = [c for c in CartItem._meta.constraints if isinstance(c, dj_models.UniqueConstraint)]
        cart_sector_constraints = [c for c in constraints if set(c.fields) == {"cart", "sector"}]
        self.assertTrue(cart_sector_constraints, "Falta UniqueConstraint(fields=['cart','sector']) en CartItem")


class ReservedAtRemovalTests(BaseCheckoutSetupMixin, TestCase):
    """2.3: reserved_at eliminado del modelo y del serializer."""

    def setUp(self):
        self.setup_base()

    def test_cartitem_has_no_reserved_at_field(self):
        self.assertNotIn("reserved_at", [f.name for f in CartItem._meta.fields])

    def test_cart_serializer_does_not_expose_reserved_at(self):
        self.add_item(1)
        resp = self.client.get(reverse("tickets:cart-my-cart"), format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        for item in resp.data["items"]:
            self.assertNotIn("reserved_at", item)
