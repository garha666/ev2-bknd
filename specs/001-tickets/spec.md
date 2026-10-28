# Spec 001: Sistema de Venta de Entradas para Conciertos y Eventos

## 1. Visión General y Roles
El sistema gestiona la reserva y compra de tickets para conciertos.
- **PÚBLICO**: Consulta libre de eventos y sectores.
- **ESPECTADOR**: Maneja su carro de tickets persistente (1:1 en DB), realiza el checkout/pago y consulta sus entradas compradas.
- **ORGANIZADOR**: Administra eventos, recintos y sectores, y gestiona el estado de las órdenes.

## 2. Requisitos Funcionales y Endpoints
### A. Catálogo (Público)
- `GET /api/eventos/`: Listar eventos con filtros (por categoría, nombre, rango de precios).
- `GET /api/eventos/{id}/sectores/`: Consultar los sectores y disponibilidad de stock/entradas de un evento.

### B. Carro de Compras Persistente (Espectador - Protegido)
- `GET /api/carro-tickets/`: Obtener el carro activo del usuario (relación 1 a 1 en PostgreSQL, persiste post-logout).
- `POST /api/carro-tickets/`: Agregar sectores y cantidad al carro.
- `DELETE /api/carro-tickets/{item_id}/`: Eliminar un ítem del carro.

### C. Checkout, Pago y Entradas (Espectador - Protegido)
- `POST /api/compras/pagar/`:
  - Valida disponibilidad atómica de stock en el sector.
  - Genera registro de Orden en estado `PAGADO`.
  - Descuenta el stock de entradas del sector.
  - Emite automáticamente las entradas compradas asignando un código único (`UUID`).
- `GET /api/mis-entradas/`: Listar los tickets adquiridos por el usuario con sus códigos UUID.

### D. Gestión de Eventos y Órdenes (Organizador - Restringido)
- `POST/PUT/DELETE /api/eventos/`: Operaciones CRUD sobre eventos y recintos.
- `PATCH /api/compras/{id}/estado/`: Actualizar estado de orden (`PENDIENTE`, `PAGADO`, `ENTREGADO`, `CANCELADO`).
  - *Regla*: Si la orden se cambia a `CANCELADO`, reponer automáticamente el stock de tickets al sector.

## 3. Modelo de Datos Esperado
- `User` (con Custom Claims JWT para rol: Espectador / Organizador).
- `Recinto` y `Evento`.
- `Sector` (con `choices` para tipos de ubicación, precio y stock total).
- `Carro` (1:1 con User) y `ItemCarro`.
- `Orden` (con `CHOICES` para estados: PENDIENTE, PAGADO, ENTREGADO, CANCELADO).
- `Ticket` (con código único UUID vinculado a la orden y sector).

## 4. Estado de implementación (enfoque híbrido)

El contrato vigente mantiene las rutas del spec **y** las rutas REST originales
en inglés como aliases, para no romper integraciones existentes. Esta sección
es la fuente de verdad de la implementación.

### 4.1 Rutas del spec (implementadas)

| Spec | Implementación | Alias en inglés |
|---|---|---|
| `GET /api/eventos/` | `EventViewSet` | `GET /api/events/` |
| `GET /api/eventos/{id}/sectores/` | acción `sectores` | `GET /api/events/{id}/sectores/` |
| `GET /api/carro-tickets/` | acción `my_cart` | `GET /api/cart/my_cart/` |
| `POST /api/carro-tickets/` | acción `add_item` | `POST /api/cart/add_item/` |
| `DELETE /api/carro-tickets/{item_id}/` | `destroy_item` | `POST /api/cart/remove_item/` |
| `POST /api/compras/pagar/` | acción `pagar` (checkout + pago atómico) | `POST /api/orders/checkout/` + `POST /api/orders/{id}/pay_order/` |
| `GET /api/mis-entradas/` | `TicketViewSet` | `GET /api/tickets/` |
| `PATCH /api/compras/{id}/estado/` | acción `estado` (solo staff) | — |

### 4.2 Estados de la orden

`PENDIENTE` → `PAGADO` → `ENTREGADO`; `PAGADO`/`ENTREGADO` → `CANCELADO`.
Los estados anteriores `COMPLETADA`/`CANCELADA` fueron migrados por la
migración `0004_alter_order_status`.

### 4.3 Reglas de negocio

- `POST /api/compras/pagar/`: valida stock, descuenta inventario de forma
  atómica, emite tickets con UUID y marca la orden como `PAGADO`. Todo en una
  sola transacción.
- `pay_order` y `cancel_order` bloquean la fila de la orden con
  `select_for_update()` y revalidan el estado, por lo que son idempotentes
  frente a concurrencia (un solo pago / una sola restitución de stock).
- `PATCH /api/compras/{id}/estado/`: exclusivo de organizadores (`is_staff`).
  Al pasar a `CANCELADO` se repone el stock y se anulan los tickets una única vez.
- `Cart.status` pasa a `PROCESADO` en el checkout. `pay_order` descuenta del
  carro las cantidades exactas del snapshot de la orden.
- `add_item` valida stock acumulado (`ya_en_carro + nuevo <= disponible`) con
  bloqueo del sector, y `CartItem` tiene `UniqueConstraint(cart, sector)`.

### 4.4 JWT

`POST /api/auth/login/` emite tokens con los claims `role`
(`Espectador`/`Organizador`), `is_staff` y `username`, además de los claims
estándar de SimpleJWT.

### 4.5 Modelos

Los modelos conservan nombres en inglés (`Venue`, `Event`, `Sector`, `Cart`,
`CartItem`, `Order`, `OrderItem`, `Ticket`), equivalentes a
`Recinto`, `Evento`, `Sector`, `Carro`, `ItemCarro`, `Orden`, `ItemOrden` y
`Ticket`. El catálogo no implementa el `choices` de tipo de ubicación:
`Sector` usa `name` libre.