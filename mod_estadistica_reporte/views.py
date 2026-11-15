import logging

from django.contrib.auth.views import redirect_to_login
from django.core.paginator import Paginator
from django.db import DatabaseError
from django.db.models import Count, Q
from django.db.models.functions import ExtractMonth, ExtractYear
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import render, resolve_url
from django.utils import timezone
from django.utils.dateparse import parse_date

from mod_adopcion.models import Adopcion
from mod_casa_temporal.models import CasaTemporal
from mod_donacion.models import Donacion
from mod_refugio.models import Personal, Rescate, Tratamiento, VacunaAnimal

logger = logging.getLogger(__name__)


MESES = (
    "Enero",
    "Febrero",
    "Marzo",
    "Abril",
    "Mayo",
    "Junio",
    "Julio",
    "Agosto",
    "Septiembre",
    "Octubre",
    "Noviembre",
    "Diciembre",
)


def _conteos_por_periodo(queryset, campo_fecha, agrupar_por_mes=False):
    anotaciones = {"anio": ExtractYear(campo_fecha)}
    campos = ["anio"]
    if agrupar_por_mes:
        anotaciones["mes"] = ExtractMonth(campo_fecha)
        campos.append("mes")

    return {
        tuple(fila[campo] for campo in campos): fila["total"]
        for fila in queryset.order_by()
        .annotate(**anotaciones)
        .values(*campos)
        .annotate(total=Count("pk"))
        .order_by(*campos)
    }


def _administrador_de_sesion(request):
    usuario_sesion = request.session.get("refugio_usuario") or {}
    supabase_uid = usuario_sesion.get("id")
    if not supabase_uid:
        return redirect_to_login(
            request.get_full_path(),
            login_url=resolve_url("login_usuario"),
        )
    try:
        es_admin = Personal.objects.filter(
            id_usuario__supabase_uid=supabase_uid,
            rol="admin",
        ).exists()
    except DatabaseError:
        logger.exception("Unable to verify statistics module administrator access")
        return HttpResponse(
            "No fue posible verificar los permisos de administrador.",
            status=503,
        )
    if not es_admin:
        return HttpResponseForbidden(
            "Esta sección está disponible solo para el administrador del refugio."
        )
    return None


def estadisticas(request):
    error_response = _administrador_de_sesion(request)
    if error_response:
        return error_response

    anio_actual = timezone.localdate().year
    valor_anio = request.GET.get("anio", str(anio_actual))
    error = None
    try:
        anio_seleccionado = int(valor_anio)
        if not 1900 <= anio_seleccionado <= anio_actual + 1:
            raise ValueError
    except (TypeError, ValueError):
        anio_seleccionado = anio_actual
        error = "Selecciona un año válido."

    fuentes = {
        "rescates": (Rescate.objects.all(), "fecha_rescate"),
        "tratamientos": (Tratamiento.objects.all(), "fecha_inicio"),
        "vacunas": (VacunaAnimal.objects.filter(aplicada=True), "fecha_aplicacion"),
        "donaciones": (Donacion.objects.all(), "fecha_donacion"),
        "hogares": (CasaTemporal.objects.all(), "fecha_ingreso"),
        "adopciones": (Adopcion.objects.all(), "fecha_inicio"),
    }
    conteos_mensuales = {}
    conteos_anuales = {}
    anios_disponibles = {anio_actual, anio_seleccionado}

    for metrica, (queryset, campo_fecha) in fuentes.items():
        mensuales = _conteos_por_periodo(
            queryset,
            campo_fecha,
            agrupar_por_mes=True,
        )
        conteos_mensuales[metrica] = mensuales
        anuales = {}
        for (anio, _mes), total in mensuales.items():
            anuales[anio] = anuales.get(anio, 0) + total
        conteos_anuales[metrica] = anuales
        anios_disponibles.update(conteos_anuales[metrica])

    total_rescates_seleccionado = sum(
        conteos_mensuales["rescates"].get((anio_seleccionado, mes), 0)
        for mes in range(1, 13)
    )
    total_rescates_historico = sum(conteos_anuales["rescates"].values())

    filas_mensuales = []
    for mes, nombre_mes in enumerate(MESES, start=1):
        fila = {
            "mes": nombre_mes,
            "rescates": conteos_mensuales["rescates"].get(
                (anio_seleccionado, mes), 0
            ),
            "porcentaje_rescates": 0,
        }
        for metrica in fuentes:
            if metrica != "rescates":
                fila[metrica] = conteos_mensuales[metrica].get(
                    (anio_seleccionado, mes), 0
                )
        if total_rescates_seleccionado:
            fila["porcentaje_rescates"] = round(
                fila["rescates"] * 100 / total_rescates_seleccionado,
                1,
            )
        filas_mensuales.append(fila)

    filas_anuales = []
    for anio in sorted(anios_disponibles, reverse=True):
        fila = {
            "anio": anio,
            "porcentaje_rescates": 0,
        }
        for metrica in fuentes:
            fila[metrica] = conteos_anuales[metrica].get(anio, 0)
        if total_rescates_historico:
            fila["porcentaje_rescates"] = round(
                fila["rescates"] * 100 / total_rescates_historico,
                1,
            )
        filas_anuales.append(fila)

    resumen = {
        metrica: sum(fila[metrica] for fila in filas_mensuales)
        for metrica in fuentes
    }
    datos_grafico = {
        "etiquetas": list(MESES),
        "series": [
            {
                "nombre": nombre,
                "datos": [fila[metrica] for fila in filas_mensuales],
            }
            for metrica, nombre in (
                ("rescates", "Rescates"),
                ("tratamientos", "Tratamientos"),
                ("vacunas", "Vacunas aplicadas"),
                ("donaciones", "Donaciones"),
                ("hogares", "Hogares registrados"),
                ("adopciones", "Adopciones"),
            )
        ],
    }

    return render(
        request,
        "estadisticas.html",
        {
            "anio_seleccionado": anio_seleccionado,
            "anios_disponibles": sorted(anios_disponibles, reverse=True),
            "filas_mensuales": filas_mensuales,
            "filas_anuales": filas_anuales,
            "resumen": resumen,
            "datos_grafico": datos_grafico,
            "error": error,
        },
        status=400 if error else 200,
    )


def personal(request):
    error_response = _administrador_de_sesion(request)
    if error_response:
        return error_response

    personal = Personal.objects.select_related("id_usuario", "id_estado").order_by(
        "id_usuario__p_nombre",
        "id_usuario__ap_paterno",
        "rut_personal",
    )
    busqueda = request.GET.get("q", "").strip()
    rol_seleccionado = request.GET.get("rol", "")
    etiquetas_rol = dict(Personal.ROLES)
    roles_disponibles = [
        (rol, etiquetas_rol.get(rol, rol.replace("_", " ").capitalize()))
        for rol in personal.order_by()
        .values_list("rol", flat=True)
        .distinct()
        .order_by("rol")
    ]

    if busqueda:
        personal = personal.filter(
            Q(id_usuario__p_nombre__icontains=busqueda)
            | Q(id_usuario__s_nombre__icontains=busqueda)
            | Q(id_usuario__ap_paterno__icontains=busqueda)
            | Q(id_usuario__ap_materno__icontains=busqueda)
            | Q(id_usuario__correo__icontains=busqueda)
        )
    valores_rol = {valor for valor, _etiqueta in roles_disponibles}
    if rol_seleccionado in valores_rol:
        personal = personal.filter(rol=rol_seleccionado)
    else:
        rol_seleccionado = ""

    cantidad_personal = personal.count()
    cantidad_activa = personal.filter(
        id_estado__nombre__iexact="Activo",
        fecha_salida__isnull=True,
    ).count()
    pagina = Paginator(personal, 20).get_page(request.GET.get("pagina"))

    return render(
        request,
        "personal.html",
        {
            "personal": pagina,
            "busqueda": busqueda,
            "rol_seleccionado": rol_seleccionado,
            "roles_disponibles": roles_disponibles,
            "cantidad_personal": cantidad_personal,
            "cantidad_activa": cantidad_activa,
        },
    )


def inventario_donaciones(request):
    error_response = _administrador_de_sesion(request)
    if error_response:
        return error_response

    busqueda = request.GET.get("q", "").strip()
    tipo_seleccionado = request.GET.get("tipo", "").strip()
    fecha_desde_texto = request.GET.get("desde", "").strip()
    fecha_hasta_texto = request.GET.get("hasta", "").strip()
    try:
        fecha_desde = parse_date(fecha_desde_texto) if fecha_desde_texto else None
        fecha_hasta = parse_date(fecha_hasta_texto) if fecha_hasta_texto else None
    except ValueError:
        fecha_desde = None
        fecha_hasta = None

    if (fecha_desde_texto and fecha_desde is None) or (
        fecha_hasta_texto and fecha_hasta is None
    ):
        return render(
            request,
            "donaciones-inventario.html",
            {
                "error": "Ingresa fechas válidas para aplicar el filtro.",
                "busqueda": busqueda,
                "tipo_seleccionado": tipo_seleccionado,
                "fecha_desde": fecha_desde_texto,
                "fecha_hasta": fecha_hasta_texto,
                "tipos_donacion": [],
                "donaciones": [],
            },
            status=400,
        )
    if fecha_desde and fecha_hasta and fecha_desde > fecha_hasta:
        return render(
            request,
            "donaciones-inventario.html",
            {
                "error": "La fecha inicial no puede ser posterior a la fecha final.",
                "busqueda": busqueda,
                "tipo_seleccionado": tipo_seleccionado,
                "fecha_desde": fecha_desde_texto,
                "fecha_hasta": fecha_hasta_texto,
                "tipos_donacion": [],
                "donaciones": [],
            },
            status=400,
        )

    try:
        donaciones_base = Donacion.objects.select_related(
            "id_usuario",
            "id_necesidad",
        )
        tipos_donacion = list(
            donaciones_base.order_by()
            .values_list("tipo_donacion", flat=True)
            .distinct()
            .order_by("tipo_donacion")
        )
        donaciones = donaciones_base
        if busqueda:
            donaciones = donaciones.filter(
                Q(tipo_donacion__icontains=busqueda)
                | Q(descripcion__icontains=busqueda)
                | Q(id_usuario__p_nombre__icontains=busqueda)
                | Q(id_usuario__s_nombre__icontains=busqueda)
                | Q(id_usuario__ap_paterno__icontains=busqueda)
                | Q(id_usuario__ap_materno__icontains=busqueda)
                | Q(id_usuario__correo__icontains=busqueda)
            )
        if tipo_seleccionado and tipo_seleccionado in tipos_donacion:
            donaciones = donaciones.filter(tipo_donacion=tipo_seleccionado)
        else:
            tipo_seleccionado = ""
        if fecha_desde:
            donaciones = donaciones.filter(fecha_donacion__gte=fecha_desde)
        if fecha_hasta:
            donaciones = donaciones.filter(fecha_donacion__lte=fecha_hasta)

        resumen = donaciones.aggregate(
            total_registros=Count("pk"),
            tipos_registrados=Count("tipo_donacion", distinct=True),
            asociadas_a_necesidad=Count(
                "pk",
                filter=Q(id_necesidad__isnull=False),
            ),
            necesidades_saciadas=Count(
                "id_necesidad",
                distinct=True,
                filter=Q(id_necesidad__saciada=True),
            ),
        )
        pagina = Paginator(
            donaciones.order_by("-fecha_donacion", "-id_donacion"),
            20,
        ).get_page(request.GET.get("pagina"))
        list(pagina.object_list)
    except DatabaseError:
        logger.exception("Unable to load the shelter donation inventory")
        return HttpResponse(
            "No fue posible cargar el inventario de donaciones.",
            status=503,
        )

    return render(
        request,
        "donaciones-inventario.html",
        {
            "donaciones": pagina,
            "tipos_donacion": tipos_donacion,
            "tipo_seleccionado": tipo_seleccionado,
            "busqueda": busqueda,
            "fecha_desde": fecha_desde_texto,
            "fecha_hasta": fecha_hasta_texto,
            "resumen": resumen,
        },
    )
