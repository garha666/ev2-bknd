"""Tests de las vistas HTML (frontend server-rendered)."""

from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Event, Order, Sector, Ticket, Venue


class WebViewsTests(TestCase):
    def setUp(self):
        self.venue = Venue.objects.create(
            name="Movistar Arena",
            address="Av. Siempre Viva 123",
            city="Santiago",
            capacity=500,
        )
        self.event = Event.objects.create(
            title="Concierto Web",
            description="Evento de prueba para las vistas HTML.",
            date=timezone.now() + timedelta(days=10),
            venue=self.venue,
        )
        self.sector = Sector.objects.create(
            event=self.event,
            name="VIP",
            price=50,
            capacity=10,
            available_stock=10,
        )

    def test_home_muestra_footer_del_alumno(self):
        response = self.client.get(reverse('web:home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Matías Antonio Gubelin Ramírez")
        self.assertContains(response, "IEC-N4-C1")
        self.assertContains(response, "2026")

    def test_evento_detalle_es_publico(self):
        response = self.client.get(
            reverse('web:event_detail', args=[self.event.id])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Concierto Web")
        self.assertContains(response, "VIP")

    def test_carro_anonimo_redirige_al_login(self):
        response = self.client.get(reverse('web:cart_detail'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_flujo_web_completo_de_compra(self):
        # 1. Registro (inicia sesión automáticamente)
        response = self.client.post(reverse('web:register'), {
            'username': 'webuser',
            'first_name': 'Web',
            'last_name': 'User',
            'email': 'web@example.com',
            'password1': 'ClaveSegura123!',
            'password2': 'ClaveSegura123!',
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(username='webuser').exists())

        # 2. Agregar al carro
        response = self.client.post(
            reverse('web:add_to_cart', args=[self.sector.id]),
            {'quantity': 2, 'event_id': self.event.id},
        )
        self.assertEqual(response.status_code, 302)

        # 3. Checkout: genera orden PENDIENTE
        response = self.client.post(reverse('web:checkout'))
        self.assertEqual(response.status_code, 302)
        order = Order.objects.get(user__username='webuser')
        self.assertEqual(order.status, 'PENDIENTE')

        # 4. Pago: descuenta stock y emite tickets
        response = self.client.post(
            reverse('web:pay_order', args=[order.id])
        )
        self.assertEqual(response.status_code, 302)

        order.refresh_from_db()
        self.sector.refresh_from_db()
        self.assertEqual(order.status, 'PAGADO')
        self.assertEqual(self.sector.available_stock, 8)
        self.assertEqual(
            Ticket.objects.filter(user__username='webuser').count(), 2
        )

        # 5. Mis entradas muestra el sector comprado
        response = self.client.get(reverse('web:my_tickets'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "VIP")

    def test_panel_requiere_staff(self):
        User.objects.create_user(username='normal', password='ClaveSegura123!')
        self.client.login(username='normal', password='ClaveSegura123!')

        response = self.client.get(reverse('web:panel'))
        self.assertEqual(response.status_code, 302)

    def _login_organizador(self):
        User.objects.create_user(
            username='organizador',
            password='ClaveSegura123!',
            is_staff=True,
        )
        self.client.login(username='organizador', password='ClaveSegura123!')

    def test_panel_muestra_formulario_para_crear_recinto(self):
        self._login_organizador()

        response = self.client.get(reverse('web:panel'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Crear recinto')
        self.assertContains(response, 'Crear evento')

    def test_panel_crea_recinto(self):
        self._login_organizador()

        response = self.client.post(reverse('web:panel_venue_create'), {
            'name': 'Estadio Nuevo',
            'address': 'Calle 123',
            'city': 'Valparaíso',
            'capacity': 2000,
        })

        self.assertRedirects(response, reverse('web:panel'))
        venue = Venue.objects.get(name='Estadio Nuevo')
        self.assertEqual(venue.city, 'Valparaíso')
        self.assertEqual(venue.capacity, 2000)
