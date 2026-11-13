import logging

from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.db import DatabaseError, transaction
from django.db.models import Q
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render, resolve_url
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from mod_refugio.models import Animal, Personal, Rescate, Usuario, VacunaAnimal

from .forms import (
    FechaTerminoAdopcionForm,
    SolicitudAdopcionForm,
    SolicitudDevolucionAdopcionForm,
)
from .models import (
    Adopcion,
    DevolucionAdopcion,
    Estado,
    ESTADO_ANIMAL_OCULTO_ID,
    SeguimientoAdopcion,
    SolicitudAdopcion,
)

logger = logging.getLogger(__name__)


def _adopcion_finalizada(fecha_termino, fecha_actual=None):
    if fecha_actual is None:
        fecha_actual = timezone.localdate()
    return fecha_termino is not None and fecha_termino <= fecha_actual


def _ids_adopciones_finalizadas(adopciones, fecha_actual=None):
    if fecha_actual is None:
        fecha_actual = timezone.localdate()
    return {
        adopcion.id_adopcion
        for adopcion in adopciones
        if _adopcion_finalizada(adopcion.fecha_termino, fecha_actual)
    }


def _estado_animal_disponible():
    return Estado.objects.filter(
        tipo_estado="Animal",
        nombre="Disponible",
    ).order_by("id_estado").first()


def _personal_access_denied(request):
    session_user = request.session.get("refugio_usuario") or {}
    supabase_uid = session_user.get("id")
    if not supabase_uid:
        return redirect_to_login(
            request.get_full_path(),
            login_url=resolve_url("login_usuario"),
        )
    if not Personal.objects.filter(
        id_usuario__supabase_uid=supabase_uid
    ).exists():
        return HttpResponseForbidden("Esta sección está disponible para el personal.")
    return None


def animales_adopcion(request):
    estado_disponible = _estado_animal_disponible()
    if estado_disponible is None:
        logger.error("Available animal state is missing from the database")
        return render(
            request,
            "catalogo-animales-adopcion.html",
            {
                "animales": [],
                "especies": [],
                "error": "El catálogo no está disponible porque falta configurar "
                "el estado Disponible para animales.",
            },
            status=503,
        )
    animales = Animal.objects.filter(
        id_estado=estado_disponible.pk
    ).select_related("raza").order_by("id_animal")
    especies = (
        Animal.objects.order_by()
        .values_list("especie", flat=True)
        .distinct()
    )
    return render(
        request,
        "catalogo-animales-adopcion.html",
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
    rescate = (
        Rescate.objects.select_related(
            "id_estado",
            "rut_personal",
            "rut_personal__id_usuario",
        )
        .filter(pk=animal.id_rescate)
        .first()
    )
    personal_nombre = None
    if rescate and rescate.rut_personal.id_usuario:
        usuario = rescate.rut_personal.id_usuario
        personal_nombre = " ".join(
            parte
            for parte in (
                usuario.p_nombre,
                usuario.s_nombre,
                usuario.ap_paterno,
                usuario.ap_materno,
            )
            if parte
        )

    vacunas_animal = (
        VacunaAnimal.objects.select_related("id_vacuna")
        .filter(id_animal=animal)
    )
    session_user = request.session.get("refugio_usuario") or {}
    supabase_uid = session_user.get("id")
    puede_editar = bool(
        supabase_uid
        and Personal.objects.filter(
            id_usuario__supabase_uid=supabase_uid
        ).exists()
    )
    solicitud_existente = None
    solicitud_rechazada = None
    estado_disponible = _estado_animal_disponible()
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
            "rescate": rescate,
            "personal_nombre": personal_nombre,
            "vacunas_animal": vacunas_animal,
            "solicitud_existente": solicitud_existente,
            "solicitud_rechazada": solicitud_rechazada,
            "solicitud_form": SolicitudAdopcionForm(),
            "puede_editar": puede_editar,
            "puede_solicitar_adopcion": (
                estado_disponible is not None
                and animal.id_estado == estado_disponible.pk
            ),
        },
    )

def listar_seguimientos(request):
    access_denied = _personal_access_denied(request)
    if access_denied:
        return access_denied

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

    adopciones = list(adopciones)
    return render(
        request,
        "seguimiento-adopciones.html",
        {
            "adopciones": adopciones,
            "adopciones_finalizadas": _ids_adopciones_finalizadas(adopciones),
        }
    )


def detalle_adopcion(request, id_adopcion):
    access_denied = _personal_access_denied(request)
    if access_denied:
        return access_denied

    adopcion = get_object_or_404(
        Adopcion.objects.select_related(
            "id_animal",
            "id_usuario"
        ),
        id_adopcion=id_adopcion
    )

    seguimientos = (
        SeguimientoAdopcion.objects
        .select_related("id_estado")
        .filter(id_adopcion_id=id_adopcion)
        .order_by("-fecha")
    )

    estados_seguimiento = Estado.objects.filter(
        tipo_estado="Seguimiento"
    ).order_by("nombre")

    return render(
        request,
        "detalle-adopcion.html",
        {
            "adopcion": adopcion,
            "adopcion_finalizada": _adopcion_finalizada(
                adopcion.fecha_termino
            ),
            "seguimientos": seguimientos,
            "es_personal": True,
            "estados_seguimiento": estados_seguimiento,
        }
    )


@require_POST
def editar_fecha_termino(request, id_adopcion):
    access_denied = _personal_access_denied(request)
    if access_denied:
        return access_denied

    adopcion = get_object_or_404(Adopcion, id_adopcion=id_adopcion)
    form = FechaTerminoAdopcionForm(
        request.POST,
        fecha_inicio=adopcion.fecha_inicio,
    )
    detalle_url = reverse(
        "mod_adopcion:detalle_adopcion",
        args=(id_adopcion,),
    )
    if not form.is_valid():
        messages.error(
            request,
            form.errors["fecha_termino"][0],
        )
        return redirect(f"{detalle_url}#fecha-termino")

    adopcion.fecha_termino = form.cleaned_data["fecha_termino"]
    try:
        adopcion.save(update_fields=("fecha_termino",))
    except DatabaseError:
        logger.exception(
            "No se pudo actualizar la fecha de término de la adopción %s",
            id_adopcion,
        )
        messages.error(request, "No se pudo actualizar la fecha de término.")
        return redirect(f"{detalle_url}#fecha-termino")

    if adopcion.fecha_termino is None:
        messages.success(
            request,
            "Se quitó la fecha de término y la adopción continúa en proceso.",
        )
    else:
        messages.success(
            request,
            "Se actualizó la fecha de término de la adopción.",
        )
    return redirect(f"{detalle_url}#fecha-termino")


@require_POST
def agregar_seguimiento(request, id_adopcion):
    access_denied = _personal_access_denied(request)
    if access_denied:
        return access_denied

    adopcion = get_object_or_404(
        Adopcion,
        id_adopcion=id_adopcion
    )

    llamada = request.POST.get("llamada") == "on"
    visita = request.POST.get("visita") == "on"
    anotacion = request.POST.get("anotacion", "").strip()
    evidencia = request.POST.get("evidencia", "").strip()

    estado_id = request.POST.get("id_estado")

    # Comprobar que se registró una llamada o visita
    if not llamada and not visita:
        messages.error(
            request,
            "Debes seleccionar una llamada, una visita o ambas."
        )
        return redirect(
            reverse(
                "mod_adopcion:detalle_adopcion",
                args=(id_adopcion,)
            )
        )

    # El estado debe pertenecer al tipo Seguimiento
    estado = get_object_or_404(
        Estado,
        id_estado=estado_id,
        tipo_estado="Seguimiento"
    )

    try:
        with transaction.atomic():
            SeguimientoAdopcion.objects.create(
                id_adopcion=adopcion,
                fecha=timezone.localdate(),
                llamada=llamada,
                visita=visita,
                anotacion=anotacion or None,
                evidencia=evidencia or None,
                id_estado=estado,
            )

        messages.success(
            request,
            "El seguimiento se registró correctamente."
        )

    except DatabaseError:
        logger.exception(
            "Error al registrar seguimiento de adopción %s",
            id_adopcion
        )
        messages.error(
            request,
            "No fue posible registrar el seguimiento."
        )

    return redirect(
        reverse(
            "mod_adopcion:detalle_adopcion",
            args=(id_adopcion,)
        )
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
    adopciones = list(adopciones)
    devoluciones = DevolucionAdopcion.objects.filter(
        id_adopcion_id__in=[
            adopcion.id_adopcion for adopcion in adopciones
        ]
    ).values_list("id_adopcion_id", "id_estado__nombre")
    devoluciones_por_estado = {
        "devoluciones_solicitadas": set(),
        "devoluciones_aprobadas": set(),
        "devoluciones_rechazadas": set(),
    }
    for id_adopcion, estado in devoluciones:
        devoluciones_por_estado["devoluciones_solicitadas"].add(id_adopcion)
        if estado == "Aprobada":
            devoluciones_por_estado["devoluciones_aprobadas"].add(id_adopcion)
        elif estado == "Rechazada":
            devoluciones_por_estado["devoluciones_rechazadas"].add(id_adopcion)

    adopciones_finalizadas = _ids_adopciones_finalizadas(adopciones)
    return render(
        request,
        "mis-adopciones.html",
        {
            "adopciones": adopciones,
            "adopciones_finalizadas": adopciones_finalizadas,
            **devoluciones_por_estado,
        }
    )


@require_POST
def solicitar_devolucion(request, id_adopcion):
    session_user = request.session.get("refugio_usuario") or {}
    supabase_uid = session_user.get("id")

    if not supabase_uid:
        return redirect_to_login(
            request.get_full_path(),
            login_url=resolve_url("login_usuario"),
        )

    form = SolicitudDevolucionAdopcionForm(request.POST)
    if not form.is_valid():
        messages.error(
            request,
            "Completa correctamente los datos de la solicitud de devolución.",
        )
        return redirect("mod_adopcion:mis_solicitudes")

    try:
        with transaction.atomic():
            adopcion = get_object_or_404(
                Adopcion.objects.select_for_update().filter(
                    Q(fecha_termino__isnull=True)
                    | Q(fecha_termino__gt=timezone.localdate())
                ),
                id_adopcion=id_adopcion,
                id_usuario__supabase_uid=supabase_uid,
            )
            ya_solicitada = DevolucionAdopcion.objects.filter(
                id_adopcion=adopcion
            ).exists()
            if ya_solicitada:
                messages.info(
                    request,
                    "Ya existe una solicitud de devolución para esta adopción.",
                )
                return redirect("mod_adopcion:mis_solicitudes")

            estado_registrada = Estado.objects.filter(
                tipo_estado="Devolucion",
                nombre="Registrada",
            ).order_by("id_estado").first()
            if estado_registrada is None:
                logger.error(
                    "Return request state 'Registrada' is missing for adoption %s",
                    id_adopcion,
                )
                messages.error(
                    request,
                    "No es posible enviar la solicitud porque el refugio no tiene "
                    "configurado el estado Registrada para devoluciones.",
                )
                return redirect("mod_adopcion:mis_solicitudes")

            datos = form.cleaned_data
            DevolucionAdopcion.objects.create(
                fecha_devolucion=timezone.localdate(),
                motivo=datos["motivo"],
                condicion_animal=datos["condicion_animal"],
                observacion=datos["observacion"],
                requiere_tratamiento=datos["requiere_tratamiento"],
                fecha_evaluacion=None,
                id_adopcion=adopcion,
                id_estado=estado_registrada,
            )
    except DatabaseError:
        logger.exception(
            "Unable to create return request for adoption %s and user %s",
            id_adopcion,
            supabase_uid,
        )
        messages.error(
            request,
            "No pudimos enviar la solicitud de devolución. Inténtalo nuevamente más tarde.",
        )
        return redirect("mod_adopcion:mis_solicitudes")

    messages.success(
        request,
        "Tu solicitud de devolución fue enviada al refugio para su evaluación.",
    )
    return redirect("mod_adopcion:mis_solicitudes")


def mis_solicitudes(request):
    session_user = request.session.get("refugio_usuario") or {}
    supabase_uid = session_user.get("id")

    if not supabase_uid:
        return redirect_to_login(
            request.get_full_path(),
            login_url=resolve_url("login_usuario"),
        )

    solicitudes = (
        SolicitudAdopcion.objects
        .filter(id_usuario__supabase_uid=supabase_uid)
        .select_related("id_animal", "id_estado")
        .order_by("-fecha_solicitud", "-id_solicitud_adopcion")
    )

    return render(
        request,
        "mis-solicitudes-adopcion.html",
        {"solicitudes": solicitudes},
    )


@require_POST
def solicitar_adopcion(request, animal_id):
    animal = get_object_or_404(Animal, id_animal=animal_id)
    detalle_url = reverse("mod_adopcion:detalle_animal", args=(animal_id,))
    estado_disponible = _estado_animal_disponible()
    puede_solicitar_adopcion = (
        estado_disponible is not None
        and animal.id_estado == estado_disponible.pk
    )
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
                "puede_solicitar_adopcion": puede_solicitar_adopcion,
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
                "puede_solicitar_adopcion": puede_solicitar_adopcion,
            },
            status=400,
        )

    try:
        with transaction.atomic():
            animal_bloqueado = Animal.objects.select_for_update().get(pk=animal.pk)
            already_requested = SolicitudAdopcion.objects.filter(
                id_animal=animal_bloqueado,
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

            estado_disponible = _estado_animal_disponible()
            if estado_disponible is None:
                logger.error("Available animal state is missing from the database")
                messages.error(
                    request,
                    "No es posible enviar la solicitud porque el refugio no tiene "
                    "configurado el estado Disponible para animales.",
                )
                return redirect(detalle_url)
            if animal_bloqueado.id_estado != estado_disponible.pk:
                messages.info(
                    request,
                    "Este animal ya no está disponible para recibir solicitudes.",
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
                        "puede_solicitar_adopcion": puede_solicitar_adopcion,
                    },
                    status=503,
                )

            SolicitudAdopcion.objects.create(
                id_animal=animal_bloqueado,
                id_usuario=usuario,
                motivo=form.cleaned_data["motivo"],
                observacion=form.cleaned_data["observacion"],
                id_estado=estado_pendiente,
                fecha_solicitud=timezone.localdate(),
            )
            animal_bloqueado.id_estado = ESTADO_ANIMAL_OCULTO_ID
            animal_bloqueado.save(update_fields=("id_estado",))
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
    return redirect("mod_adopcion:mis_solicitudes")
