"""Formularios HTML (server-rendered) del frontend de la plataforma."""

from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User

from .models import Event, Order, Sector, Venue


class LoginForm(AuthenticationForm):
    """Inicio de sesión por sesión de Django para las vistas HTML."""

    username = forms.CharField(
        label='Usuario',
        widget=forms.TextInput(attrs={'autofocus': True, 'placeholder': 'Tu usuario'}),
    )
    password = forms.CharField(
        label='Contraseña',
        widget=forms.PasswordInput(attrs={'placeholder': 'Tu contraseña'}),
    )


class RegisterForm(UserCreationForm):
    """Registro de nuevos espectadores."""

    email = forms.EmailField(required=False, label='Correo')
    first_name = forms.CharField(required=False, label='Nombres')
    last_name = forms.CharField(required=False, label='Apellidos')

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'password1', 'password2']


class AddToCartForm(forms.Form):
    """Cantidad de entradas a agregar al carro."""

    quantity = forms.IntegerField(min_value=1, initial=1, label='Cantidad')


class EventForm(forms.ModelForm):
    """Alta de eventos desde el panel del organizador."""

    class Meta:
        model = Event
        fields = ['title', 'description', 'date', 'venue']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'date': forms.DateTimeInput(
                attrs={'type': 'datetime-local'},
                format='%Y-%m-%dT%H:%M',
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['date'].input_formats = ['%Y-%m-%dT%H:%M']


class VenueForm(forms.ModelForm):
    """Alta de recintos desde el panel del organizador."""

    class Meta:
        model = Venue
        fields = ['name', 'address', 'city', 'capacity']


class SectorForm(forms.ModelForm):
    """Alta de sectores/localidades desde el panel del organizador."""

    class Meta:
        model = Sector
        fields = ['event', 'name', 'price', 'capacity', 'available_stock']


class OrderStatusForm(forms.Form):
    """Cambio de estado de una orden por parte del organizador."""

    status = forms.ChoiceField(choices=Order.STATUS, label='Nuevo estado')
