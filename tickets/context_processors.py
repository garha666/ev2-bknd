"""Context processor que inyecta los datos del alumno en todas las plantillas."""

from .constants import ALUMNO


def alumno_context(request):
    """Expone los datos del alumno para el footer obligatorio de la EVA-2."""
    return {
        'alumno': ALUMNO,
        'alumno_nombre': ALUMNO['nombre_completo'],
        'alumno_seccion': ALUMNO['seccion'],
        'alumno_anio': ALUMNO['año'],
    }
