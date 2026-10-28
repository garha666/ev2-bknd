# Tareas: Spec 001 - Venta de Entradas

- [x] **T1: Configuración de Base de Datos PostgreSQL y Variables Base**[cite: 3]
  - **Descripción**: Configurar `settings.py` para conectar Django con PostgreSQL nativo y asegurar que `drf-spectacular` y `rest_framework_simplejwt` estén listos.
  - **Hecho cuando**: El comando `python manage.py check` corra sin errores de conexión a PostgreSQL.

- [x] **T2: Creación de Modelos de Base de Datos y CHOICES**[cite: 2, 8]
  - **Descripción**: Definir en `tickets/models.py` los modelos `Recinto`, `Evento`, `Sector` (con `CHOICES` de ubicación y stock), `Carro` (relación 1:1 con Usuario), `ItemCarro`, `Orden` (con `CHOICES` de estados: PENDIENTE, PAGADO, ENTREGADO, CANCELADO) y `Ticket` (con UUID).
  - **Hecho cuando**: Las migraciones se generen y apliquen correctamente con `python manage.py makemigrations` y `python manage.py migrate`.

- [x] **T3: Configuración de Autenticación JWT con Roles Personalizados**[cite: 2, 8]
  - **Descripción**: Implementar el serializador de Token personalizado para incluir los *claims* de rol (*Espectador* o *Organizador*) en el payload del JWT.
  - **Hecho cuando**: Al hacer POST a `/api/token/`, la respuesta incluya el token de acceso y el rol del usuario.

- [x] **T4: Implementación de Endpoints Públicos y de Carro Persistente**[cite: 3, 10]
  - **Descripción**: Crear los serializers y views para listar eventos/sectores públicamente y gestionar el carro de compras persistente 1:1 del espectador.
  - **Hecho cuando**: Un usuario autenticado pueda agregar y ver ítems en su carro de compras que persistan tras cerrar sesión.

- [x] **T5: Lógica Transaccional de Checkout, Descuento de Stock y Reversión**[cite: 3, 8]
  - **Descripción**: Implementar el endpoint transaccional de pago. Al pasar a PAGADO, valida stock, lo descuenta de forma atómica y emite los tickets con UUID. Si cambia a CANCELADO, repone el stock.
  - **Hecho cuando**: La prueba de pago descuente el inventario correctamente del sector y la cancelación lo devuelva de forma automática.

- [x] **T6: Documentación Swagger y Requisitos Visuales (Footer/Datos de Alumno)**[cite: 3, 4]
  - **Descripción**: Habilitar Swagger en `/api/docs/` mediante `drf-spectacular` e incluir los datos del alumno (Nombre Completo, Sección y Año) en la vista base o pie de página.
  - **Hecho cuando**: La ruta `/api/docs/` abra la documentación interactiva y la pauta visual esté completa.# src/tickets/models.py

