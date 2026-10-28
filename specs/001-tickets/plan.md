# Plan de Implementación: Spec 001 - Venta de Entradas

## 1. Archivos a Modificar / Crear en Django (`tickets/`)
- **`models.py`**:
  - Definir modelo `Recinto` y `Evento`.
  - Definir modelo `Sector` (con atributo `CHOICES` para tipos de ubicación, precio y stock).
  - Definir modelo `Carro` (Relación OneToOne con `User`) y `ItemCarro`.
  - Definir modelo `Orden` (con atributo `CHOICES` para estados: `PENDIENTE`, `PAGADO`, `ENTREGADO`, `CANCELADO`).
  - Definir modelo `Ticket` (con campo `UUID` único vinculado a la orden).
- **`serializers.py`**:
  - Serializadores para Eventos, Sectores, Carro, Checkout y Órdenes.
  - Configuración de claims JWT personalizados para incluir el rol (*Espectador* o *Organizador*).
- **`views.py`**:
  - Vistas basadas en DRF (`ModelViewSet` / `APIView`) aplicando permisos por roles (`IsAuthenticated`, permisos personalizados para administradores/organizadores).
  - Lógica transaccional atómica para el checkout: validación de stock, cambio a `PAGADO`, descuento de inventario y reposición automática si pasa a `CANCELADO`.
- **`urls.py`**:
  - Enrutamiento de la API y configuración de la documentación con `drf-spectacular` (`/api/docs/`).

## 2. Configuración Transversal
- **`settings.py`**: Conexión activa a PostgreSQL y configuración de SimpleJWT y DRF Spectacular.
- **Datos del Alumno**: Asegurar que en las vistas base o footer aparezca el Nombre Completo, Sección y Año requeridos por la pauta.