"""
Comando de datos de demostración para la EVA-2.

Uso:
    python manage.py seed_demo

Crea usuarios, recintos, eventos y sectores de ejemplo de forma idempotente.
"""

from datetime import timedelta

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.utils import timezone

from tickets.models import Event, Sector, Venue


class Command(BaseCommand):
    help = 'Crea datos de demostración (usuarios, recintos, eventos y sectores).'

    def handle(self, *args, **options):
        # ------------------------------------------------------------------
        # Usuarios de demostración
        # ------------------------------------------------------------------
        espectador, created = User.objects.get_or_create(
            username='espectador',
            defaults={'email': 'espectador@example.com'},
        )
        if created:
            espectador.set_password('espectador123')
            espectador.save()
            self.stdout.write('  + usuario espectador / espectador123')

        organizador, created = User.objects.get_or_create(
            username='organizador',
            defaults={'email': 'organizador@example.com'},
        )
        organizador.is_staff = True
        organizador.is_superuser = True
        organizador.set_password('organizador123')
        organizador.save()
        if created:
            self.stdout.write('  + usuario organizador / organizador123 (staff)')

        # ------------------------------------------------------------------
        # Recintos
        # ------------------------------------------------------------------
        arena, _ = Venue.objects.get_or_create(
            name='Movistar Arena',
            defaults={
                'address': 'Av. Parque O\'Higgins 1860',
                'city': 'Santiago',
                'capacity': 16000,
            },
        )
        estadio, _ = Venue.objects.get_or_create(
            name='Estadio Nacional',
            defaults={
                'address': 'Av. Grecia 2001',
                'city': 'Ñuñoa',
                'capacity': 48000,
            },
        )
        teatro, _ = Venue.objects.get_or_create(
            name='Teatro Caupolicán',
            defaults={
                'address': 'San Diego 850',
                'city': 'Santiago',
                'capacity': 4500,
            },
        )

        # ------------------------------------------------------------------
        # Eventos y sectores
        # ------------------------------------------------------------------
        now = timezone.now()
        demo_events = [
            {
                'title': 'Noche de Rock 2026',
                'description': 'Las mejores bandas del rock chileno en una noche única.',
                'date': now + timedelta(days=15),
                'venue': arena,
                'sectors': [
                    ('Cancha General', 25000, 5000, 5000),
                    ('Tribuna', 45000, 3000, 3000),
                    ('VIP', 90000, 500, 500),
                ],
            },
            {
                'title': 'Festival Electrónico Sunset',
                'description': 'DJs nacionales e internacionales hasta el amanecer.',
                'date': now + timedelta(days=30),
                'venue': estadio,
                'sectors': [
                    ('General', 30000, 12000, 12000),
                    ('Preferencial', 55000, 4000, 4000),
                    ('Backstage', 120000, 200, 200),
                ],
            },
            {
                'title': 'Comedia en Vivo',
                'description': 'Una noche de stand-up con los mejores comediantes.',
                'date': now + timedelta(days=7),
                'venue': teatro,
                'sectors': [
                    ('Platea Baja', 15000, 800, 800),
                    ('Platea Alta', 10000, 600, 600),
                ],
            },
        ]

        for data in demo_events:
            event, created = Event.objects.get_or_create(
                title=data['title'],
                defaults={
                    'description': data['description'],
                    'date': data['date'],
                    'venue': data['venue'],
                },
            )
            if created:
                self.stdout.write(f'  + evento "{event.title}"')

            for name, price, capacity, stock in data['sectors']:
                Sector.objects.get_or_create(
                    event=event,
                    name=name,
                    defaults={
                        'price': price,
                        'capacity': capacity,
                        'available_stock': stock,
                    },
                )

        self.stdout.write(self.style.SUCCESS(
            'Datos de demostración listos. '
            'Usuarios: espectador/espectador123 y organizador/organizador123.'
        ))
