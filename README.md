# EVA-2 Backend — Plataforma de Venta de Entradas para Eventos y Conciertos

Proyecto **3** de la evaluación EVA-2: backend con **Django REST Framework** y
**PostgreSQL** para la venta de entradas, con autenticación **JWT**, carro
persistente, checkout transaccional y emisión de tickets con UUID.

**Alumno:** Matías Antonio Gubelin Ramírez
**Sección:** IEC-N4-C1 · **Año:** 2026

---

## Requisitos

- Python 3.12+
- PostgreSQL 14+ (base de datos `tickets_db`)
- Dependencias de `requirements.txt`

## Instalación

```bash
# 1. Crear y activar entorno virtual (Windows)
python -m venv env
.\env\Scripts\activate

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Configurar variables de entorno (opcional en local)
copy .env.example .env

# 4. Crear la base de datos en PostgreSQL
#    CREATE DATABASE tickets_db;

# 5. Aplicar migraciones
python manage.py migrate

# 6. Crear superusuario (rol Organizador)
python manage.py createsuperuser

# 7. Ejecutar el servidor
python manage.py runserver
```

> Por defecto la conexión usa `tickets_db` / `postgres` / `postgresql` en
> `127.0.0.1:5432`. Se puede sobreescribir con las variables `DB_*`.

## Documentación y utilidades

| Recurso | URL |
|---|---|
| Catálogo HTML | `http://127.0.0.1:8000/` |
| Detalle de evento | `http://127.0.0.1:8000/eventos/{id}/` |
| Carro | `http://127.0.0.1:8000/carro/` |
| Mis órdenes | `http://127.0.0.1:8000/mis-ordenes/` |
| Mis entradas | `http://127.0.0.1:8000/mis-entradas/` |
| Login / Registro | `/login/` · `/registro/` |
| Panel organizador (staff) | `http://127.0.0.1:8000/panel/` |
| Swagger / OpenAPI | `http://127.0.0.1:8000/api/docs/` |
| Esquema OpenAPI | `http://127.0.0.1:8000/api/schema/` |
| Estado y datos del alumno | `http://127.0.0.1:8000/api/status/` |
| Administración Django | `http://127.0.0.1:8000/admin/` |

## Datos de demostración

```bash
python manage.py seed_demo
```

Crea recintos, eventos, sectores y dos usuarios de prueba:

| Usuario | Contraseña | Rol |
|---|---|---|
| `espectador` | `espectador123` | Espectador |
| `organizador` | `organizador123` | Organizador (staff) |

## Interfaz web

La web usa **sesión de Django** (formularios HTML) y la API sigue usando **JWT**.
Ambas capas comparten la misma lógica de negocio (`tickets/services.py`), por lo
que el control de stock, checkout y emisión de tickets es idéntico.

Flujo del espectador:
1. Registrarse o iniciar sesión.
2. Explorar el catálogo y filtrar por recinto o rango de precios.
3. Agregar sectores al carro (persistente en PostgreSQL).
4. Generar la orden (queda `PENDIENTE`).
5. Pagar la orden: descuenta stock y emite tickets con UUID.
6. Revisar las entradas en “Mis entradas”.

El organizador puede crear recintos, eventos y sectores, además de cambiar el
estado de las órdenes desde `/panel/` o desde el admin de Django.


## Endpoints principales

### Público
- `GET /api/eventos/`
- `GET /api/eventos/{id}/sectores/`

### Espectador (JWT, `IsAuthenticated`)
- `GET/POST /api/carro-tickets/`
- `DELETE /api/carro-tickets/{item_id}/`
- `POST /api/compras/pagar/`
- `GET /api/mis-entradas/`

### Organizador (JWT, staff)
- `POST/PUT/DELETE /api/eventos/`
- `PATCH /api/compras/{id}/estado/`

## Autenticación JWT

```http
POST /api/auth/login/
Content-Type: application/json

{ "username": "usuario", "password": "clave" }
```

La respuesta incluye `access` y `refresh`. El token incorpora los claims
`username`, `is_staff` y `role` (`Espectador` u `Organizador`).

## Reglas de negocio

- El carro es **persistente** y tiene relación **1:1** con el usuario.
- El stock **no** se descuenta al agregar al carro.
- El stock se descuenta de forma **atómica** (`select_for_update` +
  actualización condicional) únicamente al pasar la orden a **PAGADO**.
- Si no hay stock suficiente, el pago se rechaza.
- Al **CANCELAR** una orden pagada/entregada, el stock se repone y los tickets
  quedan **ANULADOS**.
- Cada ticket se emite con un **UUID único**.

## Pruebas

```bash
python manage.py test tickets
python manage.py spectacular --file schema.yaml --validate
```

## Estructura

```
ticket_project/        Configuración Django y rutas raíz
tickets/
  models.py            Venue, Event, Sector, Cart, CartItem, Order, OrderItem, Ticket
  services.py          Lógica transaccional compartida (carro, pago, stock)
  filters.py           Filtros django-filter del catálogo
  serializers.py       Serialización y claims JWT
  views.py             API REST (ViewSets)
  web_views.py         Vistas HTML (catálogo, carro, órdenes, panel)
  forms.py             Formularios HTML
  urls.py              Rutas de la API
  web_urls.py          Rutas del frontend HTML
  constants.py         Datos del alumno
  templates/tickets/   Plantillas HTML con footer
  management/commands/ seed_demo.py
  tests*.py            Pruebas automatizadas
docs/                  Documentación de la metodología
specs/                 Especificación, plan y tareas
```
