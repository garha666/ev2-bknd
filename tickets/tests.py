from django.test import TestCase, TransactionTestCase
from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from .models import Venue, Event, Sector, Cart, CartItem, Order, Ticket
from django.utils import timezone

class TicketSystemTests(TransactionTestCase): # TransactionTestCase needed for select_for_update tests
    def setUp(self):
        self.client = APIClient()

        # Setup base data
        self.venue = Venue.objects.create(name="Estadio Nacional", address="Calle 1", city="Ciudad", capacity=1000)
        self.event = Event.objects.create(title="Concierto Rock", description="Desc", date=timezone.now(), venue=self.venue)
        self.sector = Sector.objects.create(event=self.event, name="VIP", price=100.00, capacity=10, available_stock=10)

        # Users
        self.user1 = User.objects.create_user(username="user1", password="password123")
        self.user2 = User.objects.create_user(username="user2", password="password123")
        self.staff = User.objects.create_superuser(username="staff", password="password123")

    def get_jwt_token(self, user):
        # Helper to authenticate user
        response = self.client.post(reverse('tickets:token_obtain_pair'), {'username': user.username, 'password': user.password})
        return response.data['access']

    def test_full_purchase_flow(self):
        """Test the entire flow: Add to cart -> Checkout -> Pay -> Verify Ticket"""
        self.client.force_authenticate(user=self.user1)

        # 1. Add to cart (action: add_item)
        add_url = reverse('tickets:cart-add-item')
        add_resp = self.client.post(add_url, {'sector_id': self.sector.id, 'quantity': 2})
        self.assertEqual(add_resp.status_code, status.HTTP_200_OK)

        # 2. Checkout (action: checkout)
        checkout_url = reverse('tickets:order-checkout')
        checkout_resp = self.client.post(checkout_url, {})
        self.assertEqual(checkout_resp.status_code, status.HTTP_201_CREATED)
        order_id = checkout_resp.data['id']

        # 3. Pay (action: pay_order)
        pay_url = reverse('tickets:order-pay-order', kwargs={'pk': order_id})
        pay_resp = self.client.post(pay_url, {})
        self.assertEqual(pay_resp.status_code, status.HTTP_200_OK)

        # 4. Verify Stock and Tickets
        self.sector.refresh_from_db()
        self.assertEqual(self.sector.available_stock, 8)
        self.assertEqual(Ticket.objects.filter(user=self.user1).count(), 2)

    def test_stock_insufficient_at_payment(self):
        """Test that payment fails if stock is gone between add_item and pay_order"""
        self.client.force_authenticate(user=self.user1)

        # Add to cart
        add_url = reverse('tickets:cart-add-item')
        self.client.post(add_url, {'sector_id': self.sector.id, 'quantity': 10})

        # Manually deplete stock in background
        Sector.objects.filter(pk=self.sector.id).update(available_stock=0)

        # Checkout
        checkout_url = reverse('tickets:order-checkout')
        checkout_resp = self.client.post(checkout_url, {})
        order_id = checkout_resp.data['id']

        # Pay should fail
        pay_url = reverse('tickets:order-pay-order', kwargs={'pk': order_id})
        pay_resp = self.client.post(pay_url, {})
        self.assertEqual(pay_resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Stock insuficiente', pay_resp.data['error'])

    def test_idor_payment_protection(self):
        """Test that a user cannot pay for another user's order"""
        # Create order for user1
        self.client.force_authenticate(user=self.user1)
        add_url = reverse('tickets:cart-add-item')
        self.client.post(add_url, {'sector_id': self.sector.id, 'quantity': 1})
        checkout_url = reverse('tickets:order-checkout')
        checkout_resp = self.client.post(checkout_url, {})
        order_id = checkout_resp.data['id']

        # Try to pay as user2
        self.client.force_authenticate(user=self.user2)
        pay_url = reverse('tickets:order-pay-order', kwargs={'pk': order_id})
        pay_resp = self.client.post(pay_url, {})

        self.assertEqual(pay_resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_cancel_order_restores_stock(self):
        """Test that canceling a completed order restores stock"""
        self.client.force_authenticate(user=self.user1)
        add_url = reverse('tickets:cart-add-item')
        self.client.post(add_url, {'sector_id': self.sector.id, 'quantity': 5})
        checkout_url = reverse('tickets:order-checkout')
        checkout_resp = self.client.post(checkout_url, {})
        order_id = checkout_resp.data['id']

        # Complete payment
        pay_url = reverse('tickets:order-pay-order', kwargs={'pk': order_id})
        self.client.post(pay_url, {})
        self.sector.refresh_from_db()
        self.assertEqual(self.sector.available_stock, 5)

        # Cancel order
        cancel_url = reverse('tickets:order-cancel-order', kwargs={'pk': order_id})
        self.client.post(cancel_url, {})

        self.sector.refresh_from_db()
        self.assertEqual(self.sector.available_stock, 10)
        self.assertEqual(Ticket.objects.filter(order_item__order_id=order_id).first().status, 'ANULADO')
