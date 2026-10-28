"""Tests de alineación con el Spec 001 (rutas en español, estados y JWT).

Cubre el enfoque híbrido: se mantienen las rutas originales en inglés y se
agregan las del spec:
  - GET  /api/eventos/
  - GET  /api/eventos/{id}/sectores/
  - GET/POST /api/carro-tickets/
  - DELETE /api/carro-tickets/{item_id}/
  - POST /api/compras/pagar/
  - GET  /api/mis-entradas/
  - PATCH /api/compras/{id}/estado/  (solo Organizador)
  - Claims de rol en el JWT (Espectador / Organizador)
"""
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from .models import Cart, CartItem, Event, Order, Sector, Ticket, Venue


class SpecRoutesSetupMixin:
    def setup_base(self):
        self.user = User.objects.create_user(username="espectador", password="password123")
        self.staff = User.objects.create_superuser(username="organizador", password="password123")
        self.venue = Venue.objects.create(name="Movistar Arena", address="Calle 1", city="Santiago", capacity=500)
        self.event = Event.objects.create(
            title="Concierto Rock", description="Desc", date="2026-12-01T20:00:00Z", venue=self.venue
        )
        self.sector = Sector.objects.create(
            event=self.event, name="VIP", price=50, capacity=100, available_stock=10
        )
        self.client = APIClient()


class CatalogRoutesTests(SpecRoutesSetupMixin, TestCase):
    def setUp(self):
        self.setup_base()

    def test_eventos_list(self):
        response = self.client.get("/api/eventos/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        titles = [item["title"] for item in response.data]
        self.assertIn("Concierto Rock", titles)

    def test_eventos_sectores(self):
        response = self.client.get(f"/api/eventos/{self.event.id}/sectores/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data[0]["name"], "VIP")
        self.assertEqual(response.data[0]["available_stock"], 10)


class CarroTicketsRoutesTests(SpecRoutesSetupMixin, TestCase):
    def setUp(self):
        self.setup_base()
        self.client.force_authenticate(user=self.user)

    def test_get_cart_creates_and_returns_cart(self):
        response = self.client.get("/api/carro-tickets/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["items"], [])

    def test_post_adds_item(self):
        response = self.client.post(
            "/api/carro-tickets/", {"sector_id": self.sector.id, "quantity": 2}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(CartItem.objects.get(cart__user=self.user).quantity, 2)

    def test_delete_removes_item(self):
        self.client.post(
            "/api/carro-tickets/", {"sector_id": self.sector.id, "quantity": 2}, format="json"
        )
        item = CartItem.objects.get(cart__user=self.user)

        response = self.client.delete(f"/api/carro-tickets/{item.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(CartItem.objects.filter(pk=item.pk).exists())

    def test_delete_other_users_item_returns_404(self):
        other = User.objects.create_user(username="otro", password="password123")
        other_cart = Cart.objects.create(user=other)
        item = CartItem.objects.create(cart=other_cart, sector=self.sector, quantity=1)

        response = self.client.delete(f"/api/carro-tickets/{item.id}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(CartItem.objects.filter(pk=item.pk).exists())


class ComprasRoutesTests(SpecRoutesSetupMixin, TestCase):
    def setUp(self):
        self.setup_base()
        self.client.force_authenticate(user=self.user)

    def test_pagar_full_flow(self):
        """POST /api/compras/pagar/: paga, descuenta stock y emite tickets."""
        self.client.post(
            "/api/carro-tickets/", {"sector_id": self.sector.id, "quantity": 3}, format="json"
        )

        response = self.client.post("/api/compras/pagar/", {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["order"]["status"], "PAGADO")

        self.sector.refresh_from_db()
        self.assertEqual(self.sector.available_stock, 7)
        self.assertEqual(Ticket.objects.filter(user=self.user).count(), 3)
        self.assertFalse(CartItem.objects.filter(cart__user=self.user).exists())

    def test_pagar_with_empty_cart_fails(self):
        response = self.client.post("/api/compras/pagar/", {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_mis_entradas_lists_only_own_tickets(self):
        self.client.post(
            "/api/carro-tickets/", {"sector_id": self.sector.id, "quantity": 2}, format="json"
        )
        self.client.post("/api/compras/pagar/", {}, format="json")

        other = User.objects.create_user(username="otro", password="password123")
        other_ticket = Ticket.objects.create(
            order_item=Ticket.objects.first().order_item,
            sector=self.sector,
            user=other,
        )

        response = self.client.get("/api/mis-entradas/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [ticket["id"] for ticket in response.data]
        self.assertEqual(len(ids), 2)
        self.assertNotIn(other_ticket.id, ids)

    def test_mis_entradas_requires_auth(self):
        self.client.force_authenticate(user=None)
        response = self.client.get("/api/mis-entradas/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class EstadoOrdenRoutesTests(SpecRoutesSetupMixin, TestCase):
    def setUp(self):
        self.setup_base()
        self.client.force_authenticate(user=self.user)
        self.client.post(
            "/api/carro-tickets/", {"sector_id": self.sector.id, "quantity": 2}, format="json"
        )
        response = self.client.post("/api/compras/pagar/", {}, format="json")
        self.order_id = response.data["order"]["id"]

    def test_organizador_marks_entregado(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.patch(
            f"/api/compras/{self.order_id}/estado/", {"status": "ENTREGADO"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["order"]["status"], "ENTREGADO")

    def test_espectador_cannot_change_state(self):
        response = self.client.patch(
            f"/api/compras/{self.order_id}/estado/", {"status": "ENTREGADO"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(Order.objects.get(pk=self.order_id).status, "PAGADO")

    def test_cancelado_restores_stock_once_and_annuls_tickets(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.patch(
            f"/api/compras/{self.order_id}/estado/", {"status": "CANCELADO"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.sector.refresh_from_db()
        self.assertEqual(self.sector.available_stock, 10)  # 10 -> 8 -> 10
        self.assertEqual(
            Ticket.objects.filter(order_item__order_id=self.order_id, status="ANULADO").count(), 2
        )

        # Segundo intento: ya está cancelada, no debe restituir de nuevo
        second = self.client.patch(
            f"/api/compras/{self.order_id}/estado/", {"status": "CANCELADO"}, format="json"
        )
        self.assertEqual(second.status_code, status.HTTP_200_OK)  # idempotente (mismo estado)
        self.sector.refresh_from_db()
        self.assertEqual(self.sector.available_stock, 10)

    def test_invalid_status_rejected(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.patch(
            f"/api/compras/{self.order_id}/estado/", {"status": "VOLANDO"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class JwtRoleClaimsTests(SpecRoutesSetupMixin, TestCase):
    def setUp(self):
        self.setup_base()

    def _login_claims(self, username, password):
        response = self.client.post(
            "/api/auth/login/", {"username": username, "password": password}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return AccessToken(response.data["access"])

    def test_espectador_role_claim(self):
        token = self._login_claims("espectador", "password123")
        self.assertEqual(token["role"], "Espectador")
        self.assertEqual(token["username"], "espectador")
        self.assertFalse(token["is_staff"])

    def test_organizador_role_claim(self):
        token = self._login_claims("organizador", "password123")
        self.assertEqual(token["role"], "Organizador")
        self.assertTrue(token["is_staff"])
