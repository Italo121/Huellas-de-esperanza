import logging

from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.db import DatabaseError, transaction
from django.shortcuts import get_object_or_404, redirect, render, resolve_url
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from mod_refugio.models import Animal, Personal, Usuario

from .forms import RespuestaSolicitudAdopcionForm, SolicitudAdopcionForm
from .models import Adopcion, Estado, SeguimientoAdopcion, SolicitudAdopcion

logger = logging.getLogger(__name__)


def animales_adopcion(request):
    animales = Animal.objects.select_related("raza").order_by("id_animal")
    especies = (
        Animal.objects.order_by()
        .values_list("especie", flat=True)
        .distinct()
    )
    return render(
        request,
        "animales-adopcion.html",
        {
            "animales": animales,
            "especies": especies,
        },
    )

def detalle_animal(request, id_animal):
    animal = get_object_or_404(
        Animal,
        id_animal=id_animal
    )
    session_user = request.session.get("refugio_usuario") or {}
    supabase_uid = session_user.get("id")
    solicitud_existente = None
    solicitud_rechazada = None
    if supabase_uid:
        solicitud = (
            SolicitudAdopcion.objects.filter(
                id_animal=animal,
                id_usuario__supabase_uid=supabase_uid,
                id_estado__tipo_estado="Solicitud",
                id_estado__nombre__in=("Pendiente", "En Revisión", "Aprobada"),
            )
            .first()
        )
        if solicitud is None:
            solicitud_rechazada = (
                SolicitudAdopcion.objects.filter(
                    id_animal=animal,
                    id_usuario__supabase_uid=supabase_uid,
                    id_estado__tipo_estado="Solicitud",
                    id_estado__nombre="Rechazada",
                )
                .first()
            )
        if solicitud:
            solicitud_existente = solicitud

    return render(
        request,
        "detalle-animal.html",
        {
            "animal": animal,
            "solicitud_existente": solicitud_existente,
            "solicitud_rechazada": solicitud_rechazada,
            "solicitud_form": SolicitudAdopcionForm(),
        },
    )

def listar_seguimientos(request):
    adopciones = (
        Adopcion.objects
        .select_related("id_animal", "id_usuario")
        .only(
            "id_adopcion",
            "fecha_inicio",
            "fecha_termino",
            "id_animal",
            "id_animal__id_animal",
            "id_animal__nombre",
            "id_usuario",
            "id_usuario__id_usuario",
            "id_usuario__p_nombre",
            "id_usuario__ap_paterno",
        )
        .all()
        .order_by("-fecha_inicio")
    )

    return render(
        request,
        "seguimiento-adopciones.html",
        {"adopciones": adopciones}
    )

def detalle_adopcion(request, id_adopcion):
    adopcion = get_object_or_404(
        Adopcion.objects.select_related(
            "id_animal",
            "id_usuario"
        ).only(
            "id_adopcion",
            "fecha_inicio",
            "fecha_termino",
            "id_animal",
            "id_animal__id_animal",
            "id_animal__nombre",
            "id_animal__especie",
            "id_usuario",
            "id_usuario__id_usuario",
            "id_usuario__p_nombre",
            "id_usuario__s_nombre",
            "id_usuario__ap_paterno",
            "id_usuario__ap_materno",
            "id_usuario__correo",
        ),
        id_adopcion=id_adopcion
    )

    seguimientos = (
        SeguimientoAdopcion.objects
        .select_related("id_estado")
        .filter(id_adopcion_id=id_adopcion)
        .order_by("-fecha")
    )

    return render(
        request,
        "detalle-adopcion.html",
        {
            "adopcion": adopcion,
            "seguimientos": seguimientos,
        }
    )

def mis_adopciones(request):
    session_user = request.session.get("refugio_usuario") or {}
    supabase_uid = session_user.get("id")

    if not supabase_uid:
        return redirect_to_login(
            request.get_full_path(),
            login_url=resolve_url("login_usuario"),
        )

    adopciones = (
        Adopcion.objects
        .filter(id_usuario__supabase_uid=supabase_uid)
        .select_related("id_animal", "id_usuario")
        .order_by("-fecha_inicio")
    )

    return render(
        request,
        "mis-adopciones.html",
        {
            "adopciones": adopciones,
        }
    )


@require_POST
def solicitar_adopcion(request, animal_id):
    animal = get_object_or_404(Animal, id_animal=animal_id)
    detalle_url = reverse("mod_adopcion:detalle_animal", args=(animal_id,))
    session_user = request.session.get("refugio_usuario") or {}
    supabase_uid = session_user.get("id")

    if not supabase_uid:
        messages.info(request, "Inicia sesión para enviar una solicitud de adopción.")
        return redirect_to_login(
            detalle_url,
            login_url=resolve_url("login_usuario"),
        )

    try:
        usuario = Usuario.objects.get(supabase_uid=supabase_uid)
    except Usuario.DoesNotExist:
        return render(
            request,
            "detalle-animal.html",
            {
                "animal": animal,
                "solicitud_existente": None,
                "solicitud_rechazada": None,
                "solicitud_form": SolicitudAdopcionForm(request.POST),
                "error": (
                    "No pudimos verificar tu cuenta. Inicia sesión nuevamente "
                    "para enviar la solicitud."
                ),
            },
            status=403,
        )

    form = SolicitudAdopcionForm(request.POST)
    if not form.is_valid():
        return render(
            request,
            "detalle-animal.html",
            {
                "animal": animal,
                "solicitud_existente": None,
                "solicitud_rechazada": None,
                "solicitud_form": form,
            },
            status=400,
        )

    try:
        with transaction.atomic():
            Animal.objects.select_for_update().get(pk=animal.pk)
            already_requested = SolicitudAdopcion.objects.filter(
                id_animal=animal,
                id_usuario=usuario,
                id_estado__tipo_estado="Solicitud",
                id_estado__nombre__in=(
                    "Pendiente",
                    "En Revisión",
                    "Aprobada",
                ),
            ).exists()
            if already_requested:
                messages.info(
                    request,
                    "Ya tienes una solicitud pendiente o aprobada para este animal.",
                )
                return redirect(detalle_url)

            estado_pendiente = Estado.objects.filter(
                tipo_estado="Solicitud",
                nombre="Pendiente",
            ).order_by("id_estado").first()
            if estado_pendiente is None:
                logger.error(
                    "Pending adoption request state is missing from the database"
                )
                return render(
                    request,
                    "detalle-animal.html",
                    {
                        "animal": animal,
                        "solicitud_existente": None,
                        "solicitud_rechazada": None,
                        "solicitud_form": form,
                        "error": (
                            "No es posible enviar la solicitud en este momento. "
                            "El refugio debe configurar el estado Pendiente."
                        ),
                    },
                    status=503,
                )

            SolicitudAdopcion.objects.create(
                id_animal=animal,
                id_usuario=usuario,
                motivo=form.cleaned_data["motivo"],
                observacion=form.cleaned_data["observacion"],
                id_estado=estado_pendiente,
                fecha_solicitud=timezone.localdate(),
            )
    except DatabaseError:
        logger.exception(
            "Unable to save adoption request for user %s and animal %s",
            usuario.pk,
            animal.pk,
        )
        messages.error(
            request,
            "No pudimos guardar tu solicitud. Inténtalo nuevamente más tarde.",
        )
        return redirect(detalle_url)

    messages.success(
        request,
        "Tu solicitud de adopción fue enviada. El refugio la revisará.",
    )
    return redirect(detalle_url)


def gestion_solicitudes_adopcion(request):
    if request.method not in {"GET", "POST"}:
        response = render(
            request,
            "gestion_solicitudes_adopcion.html",
            {"error": "Método no permitido."},
            status=405,
        )
        response["Allow"] = "GET, POST"
        return response

    session_user = request.session.get("refugio_usuario") or {}
    supabase_uid = session_user.get("id")
    if not supabase_uid:
        messages.info(request, "Inicia sesión con una cuenta del personal para continuar.")
        return redirect_to_login(
            request.get_full_path(),
            login_url=resolve_url("login_usuario"),
        )

    personal = (
        Personal.objects.filter(
            id_usuario__supabase_uid=supabase_uid,
            id_estado__tipo_estado="Personal",
            id_estado__nombre="Activo",
        )
        .order_by("rut_personal")
        .first()
    )
    if personal is None:
        return render(
            request,
            "gestion_solicitudes_adopcion.html",
            {"error": "Esta sección está disponible para el personal activo del refugio."},
            status=403,
        )

    error = None
    form = RespuestaSolicitudAdopcionForm()
    if request.method == "POST":
        form = RespuestaSolicitudAdopcionForm(request.POST)
        solicitud_id = request.POST.get("solicitud_id")
        if not form.is_valid():
            error = "Selecciona una acción válida para responder la solicitud."
        elif not solicitud_id:
            error = "No se identificó la solicitud que quieres responder."
        else:
            try:
                with transaction.atomic():
                    solicitud = get_object_or_404(
                        SolicitudAdopcion.objects.select_for_update(),
                        pk=solicitud_id,
                    )
                    if solicitud.id_estado.nombre not in {
                        "Pendiente",
                        "En Revisión",
                    }:
                        error = "Esta solicitud ya fue respondida."
                    else:
                        estado_nombre = (
                            "Aprobada"
                            if form.cleaned_data["action"]
                            == SolicitudAdopcion.APROBADA
                            else "Rechazada"
                        )
                        estado = Estado.objects.filter(
                            tipo_estado="Solicitud",
                            nombre=estado_nombre,
                        ).order_by("id_estado").first()
                        if estado is None:
                            error = (
                                "No se encontró el estado para responder la solicitud. "
                                "No se realizó ningún cambio."
                            )
                            logger.error(
                                "Adoption request state %s is missing from the database",
                                estado_nombre,
                            )
                        else:
                            solicitud.id_estado = estado
                            solicitud.respuesta = form.cleaned_data["respuesta"]
                            solicitud.fecha_respuesta = timezone.localdate()
                            solicitud.respondida_por = personal
                            solicitud.save(
                                update_fields=(
                                    "id_estado",
                                    "respuesta",
                                    "fecha_respuesta",
                                    "respondida_por",
                                )
                            )
            except DatabaseError:
                logger.exception(
                    "Unable to respond to adoption request %s by staff member %s",
                    solicitud_id,
                    personal.pk,
                )
                error = "No pudimos guardar la respuesta. Inténtalo nuevamente."
            else:
                if error is None:
                    messages.success(request, "La solicitud fue respondida correctamente.")
                    return redirect("mod_adopcion:gestion_solicitudes_adopcion")

    solicitudes = SolicitudAdopcion.objects.select_related(
        "id_animal",
        "id_usuario",
        "id_estado",
        "respondida_por",
    )
    return render(
        request,
        "gestion_solicitudes_adopcion.html",
        {
            "error": error,
            "es_personal": True,
            "form": form,
            "solicitudes": solicitudes,
        },
        status=400 if request.method == "POST" and error else 200,
    )
