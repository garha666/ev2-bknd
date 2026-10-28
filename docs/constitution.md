# Constitución del Proyecto: Backend Venta de Tickets (EV2)

1. **Stack Simplificado**: Django + DRF + PostgreSQL nativo + JWT. Sin dependencias innecesarias.
2. **Especificación Estricta**: Cada cambio o mejora debe justificarse en un archivo `spec.md` antes de escribir código.
3. **Persistencia e Integridad**: Carro de compras persistente 1:1 en DB PostgreSQL (no dependiente de sesión temporal). Stock descontado únicamente al pasar a estado PAGADO.
4. **Seguridad y Roles**: Autenticación JWT con claims explícitos de rol (Espectador vs Organizador) y permisos DRF según la matriz dada.
5. **Calidad y Documentación**: Todo modelo, vista y serializador debe estar comentado en bloques. Pie de página o vistas base con Nombre, Sección y Año del alumno.
6. **Documentación Abierta**: Endpoint Swagger / OpenAPI plenamente operativo en `/api/docs/`.