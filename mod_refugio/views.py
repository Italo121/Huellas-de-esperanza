import json
import logging
from decimal import Decimal
from urllib.parse import urlencode
from uuid import uuid4

from httpx import ReadTimeout
from django.db import DatabaseError, transaction
from django.db.models import Exists, OuterRef
from django.http import JsonResponse
from django.contrib.auth.views import redirect_to_login
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render, resolve_url
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .forms import (
    AltaPersonalDesdeSolicitudForm,
    EditarAnimalForm,
    EvaluacionAnimalForm,
    FiltroFechaSolicitudForm,
    GestionSolicitudVoluntariadoForm,
    RegistroAnimalForm,
    RegistroUsuarioForm,
    SolicitudVoluntariadoForm,
    TratamientoAnimalForm,
    VacunaAnimalForm,
)
from .models import (
    Animal,
    EvaluacionAnimal,
    Estado,
    Personal,
    Rescate,
    Refugio,
    SolicitudVoluntariado,
    Tratamiento,
    Usuario,
    Veterinario,
    VacunaAnimal,
)
from .supabase_client import supabase, supabase_storage

logger = logging.getLogger(__name__)


def inicio(request):
    animales = (
        Animal.objects.select_related("raza")
        .order_by("id_animal")
    )
    especies = (
        Animal.objects.order_by()
        .values_list("especie", flat=True)
        .distinct()
    )
    session_user = request.session.get("refugio_usuario", {})
    supabase_uid = session_user.get("id") if session_user else None
    es_personal = bool(
        supabase_uid
        and Personal.objects.filter(
            id_usuario__supabase_uid=supabase_uid
        ).exists()
    )
    return render(
        request,
        "index.html",
        {
            "animales": animales,
            "especies": especies,
            "es_personal": es_personal,
        },
    )


def informacion_refugio(request):
    refugio = Refugio.objects.order_by("id_refugio").first()
    coordenadas_validas = False
    external_map_url = None
    if refugio and refugio.latitud is not None and refugio.longitud is not None:
        latitud = refugio.latitud
        longitud = refugio.longitud
        if Decimal("-90") <= latitud <= Decimal("90") and Decimal("-180") <= longitud <= Decimal("180"):
            coordenadas_validas = True
            external_map_url = (
                "https://www.openstreetmap.org/?"
                + urlencode({"mlat": str(latitud), "mlon": str(longitud)})
            )

    return render(
        request,
        "informacion_refugio.html",
        {
            "refugio": refugio,
            "coordenadas_validas": coordenadas_validas,
            "external_map_url": external_map_url,
        },
    )


def solicitar_voluntariado(request):
    if request.method not in {"GET", "POST"}:
        response = render(
            request,
            "solicitud_voluntariado.html",
            {"error": "Método no permitido."},
            status=405,
        )
        response["Allow"] = "GET, POST"
        return response

    session_user = request.session.get("refugio_usuario")
    if not session_user:
        messages.info(
            request,
            "Inicia sesión con tu cuenta para enviar una solicitud de voluntariado.",
        )
        return redirect_to_login(
            request.get_full_path(),
            login_url=resolve_url("login_usuario"),
        )

    supabase_uid = session_user.get("id")
    if not supabase_uid:
        return render(
            request,
            "solicitud_voluntariado.html",
            {
                "error": (
                    "No pudimos verificar tu cuenta. Inicia sesión nuevamente "
                    "para continuar."
                )
            },
            status=403,
        )

    try:
        usuario = Usuario.objects.get(supabase_uid=supabase_uid)
    except Usuario.DoesNotExist:
        return render(
            request,
            "solicitud_voluntariado.html",
            {
                "error": (
                    "No encontramos los datos asociados a tu cuenta. "
                    "Inicia sesión nuevamente o contacta al refugio."
                )
            },
            status=403,
        )

    if Personal.objects.filter(id_usuario=usuario).exists():
        return render(
            request,
            "solicitud_voluntariado.html",
            {
                "usuario": usuario,
                "ya_es_personal": True,
            },
        )

    solicitud_pendiente = (
        SolicitudVoluntariado.objects.filter(
            id_usuario=usuario,
            id_estado__tipo_estado="Solicitud",
            id_estado__nombre="Pendiente",
        )
        .order_by("-fecha_solicitud", "-id_solicitud_vol")
        .first()
    )
    form = SolicitudVoluntariadoForm()
    error = None
    response_status = 200

    if request.method == "POST" and solicitud_pendiente is None:
        form = SolicitudVoluntariadoForm(request.POST)
        if form.is_valid():
            estado_pendiente = (
                Estado.objects.filter(
                    tipo_estado="Solicitud",
                    nombre="Pendiente",
                )
                .order_by("id_estado")
                .first()
            )
            if estado_pendiente is None:
                error = (
                    "No es posible enviar la solicitud en este momento. "
                    "Inténtalo más tarde."
                )
                response_status = 503
                logger.error(
                    "Pending volunteer application state is missing from the database"
                )
            else:
                solicitud = form.save(commit=False)
                solicitud.fecha_solicitud = timezone.localdate()
                solicitud.id_usuario = usuario
                solicitud.id_estado = estado_pendiente
                try:
                    solicitud.save()
                except DatabaseError:
                    logger.exception(
                        "Unable to save volunteer application for user %s",
                        usuario.pk,
                    )
                    error = (
                        "No pudimos enviar tu solicitud. Revisa los datos "
                        "e inténtalo nuevamente."
                    )
                    response_status = 500
                else:
                    messages.success(
                        request,
                        "Tu solicitud para unirte al refugio fue enviada correctamente.",
                    )
                    return redirect("solicitar_voluntariado")

    return render(
        request,
        "solicitud_voluntariado.html",
        {
            "form": form,
            "error": error,
            "solicitud_pendiente": solicitud_pendiente,
            "usuario": usuario,
        },
        status=(
            400
            if request.method == "POST" and form.errors
            else response_status
        ),
    )


def gestion_solicitudes(request):
    if request.method not in {"GET", "POST"}:
        response = render(
            request,
            "gestion_solicitudes.html",
            {"error": "Método no permitido."},
            status=405,
        )
        response["Allow"] = "GET, POST"
        return response

    session_user = request.session.get("refugio_usuario")
    if not session_user:
        messages.info(request, "Inicia sesión con una cuenta del personal para continuar.")
        return redirect_to_login(
            request.get_full_path(),
            login_url=resolve_url("login_usuario"),
        )

    supabase_uid = session_user.get("id")
    if not supabase_uid:
        return render(
            request,
            "gestion_solicitudes.html",
            {"error": "No pudimos verificar tu cuenta. Inicia sesión nuevamente."},
            status=403,
        )

    try:
        personal = Personal.objects.get(id_usuario__supabase_uid=supabase_uid)
    except Personal.DoesNotExist:
        return render(
            request,
            "gestion_solicitudes.html",
            {"error": "Esta sección está disponible para el personal del refugio."},
            status=403,
        )

    es_admin = personal.rol == "admin"
    solicitud_form = GestionSolicitudVoluntariadoForm()
    personal_form = AltaPersonalDesdeSolicitudForm()
    filtro_fecha_form = FiltroFechaSolicitudForm(request.GET or None)
    error = None
    if request.method == "POST":
        solicitud = get_object_or_404(
            SolicitudVoluntariado.objects.select_related("id_estado", "id_usuario"),
            pk=request.POST.get("solicitud_id"),
        )
        if Personal.objects.filter(id_usuario=solicitud.id_usuario).exists():
            error = (
                "Esta persona ya forma parte del personal. "
                "La solicitud no puede volver a modificarse."
            )
        elif request.POST.get("action") == "incorporar_personal":
            if not es_admin:
                error = "Solo una cuenta admin puede incorporar personal."
            elif solicitud.id_estado.nombre != "Aprobada":
                error = (
                    "La solicitud debe estar aprobada antes de crear "
                    "el perfil de personal."
                )
            else:
                personal_form = AltaPersonalDesdeSolicitudForm(request.POST)
                if personal_form.is_valid():
                    estado_activo = Estado.objects.filter(
                        tipo_estado="Personal",
                        nombre="Activo",
                    ).first()
                    if estado_activo is None:
                        error = (
                            "No se encontró el estado 'Activo' para personal. "
                            "No se realizó ningún cambio."
                        )
                        logger.error(
                            "Active staff state is missing while incorporating approved application %s",
                            solicitud.pk,
                        )
                    else:
                        datos_personal = personal_form.cleaned_data
                        try:
                            with transaction.atomic():
                                Personal.objects.create(
                                    rut_personal=datos_personal["rut_personal"],
                                    rol=datos_personal["rol"],
                                    fecha_ingreso=timezone.localdate(),
                                    telefono_emergencia=datos_personal[
                                        "telefono_emergencia"
                                    ],
                                    direccion=datos_personal["direccion"],
                                    id_usuario=solicitud.id_usuario,
                                    id_estado=estado_activo,
                                    id_solicitud_vol=solicitud,
                                )
                        except DatabaseError:
                            logger.exception(
                                "Unable to create staff profile from approved application %s by admin %s",
                                solicitud.pk,
                                personal.pk,
                            )
                            error = (
                                "No pudimos crear el perfil de personal. "
                                "Revisa los datos e inténtalo nuevamente."
                            )
                        else:
                            messages.success(
                                request,
                                "El perfil de personal se creó correctamente.",
                            )
                            return _redirect_to_filtered_solicitudes(request)
        else:
            solicitud_form = GestionSolicitudVoluntariadoForm(
                request.POST,
                instance=solicitud,
            )
            if solicitud_form.is_valid():
                solicitud_actualizada = solicitud_form.save(commit=False)
                solicitud_actualizada.fecha_respuesta = (
                    None
                    if solicitud_actualizada.id_estado.nombre == "Pendiente"
                    else timezone.localdate()
                )
                try:
                    solicitud_actualizada.save(
                        update_fields=("id_estado", "observacion", "fecha_respuesta")
                    )
                except DatabaseError:
                    logger.exception(
                        "Unable to update volunteer application %s by staff %s",
                        solicitud.pk,
                        personal.pk,
                    )
                    error = "No pudimos actualizar la solicitud. Inténtalo nuevamente."
                else:
                    messages.success(request, "La solicitud se actualizó correctamente.")
                    return _redirect_to_filtered_solicitudes(request)

    solicitudes_voluntariado = (
        SolicitudVoluntariado.objects.select_related("id_usuario", "id_estado")
        .annotate(
            ya_es_personal=Exists(
                Personal.objects.filter(id_usuario_id=OuterRef("id_usuario_id"))
            )
        )
        .order_by("-fecha_solicitud", "-id_solicitud_vol")
    )
    if filtro_fecha_form.is_valid():
        fecha_desde = filtro_fecha_form.cleaned_data.get("fecha_desde")
        fecha_hasta = filtro_fecha_form.cleaned_data.get("fecha_hasta")
        if fecha_desde:
            solicitudes_voluntariado = solicitudes_voluntariado.filter(
                fecha_solicitud__gte=fecha_desde
            )
        if fecha_hasta:
            solicitudes_voluntariado = solicitudes_voluntariado.filter(
                fecha_solicitud__lte=fecha_hasta
            )
    elif filtro_fecha_form.errors:
        solicitudes_voluntariado = solicitudes_voluntariado.none()
    return render(
        request,
        "gestion_solicitudes.html",
        {
            "solicitudes_voluntariado": solicitudes_voluntariado,
            "solicitud_form": solicitud_form,
            "personal_form": personal_form,
            "es_admin": es_admin,
            "filtro_fecha_form": filtro_fecha_form,
            "error": error,
            "personal": personal,
        },
        status=(
            400
            if solicitud_form.errors
            or (
                request.method == "POST"
                and request.POST.get("action") == "incorporar_personal"
                and personal_form.errors
            )
            or filtro_fecha_form.errors
            else 200
        ),
    )


def _redirect_to_filtered_solicitudes(request):
    query_params = {
        key: value
        for key, value in {
            "fecha_desde": request.POST.get("fecha_desde", ""),
            "fecha_hasta": request.POST.get("fecha_hasta", ""),
        }.items()
        if value
    }
    destination = resolve_url("gestion_solicitudes")
    if query_params:
        destination = f"{destination}?{urlencode(query_params)}"
    return redirect(destination)


def ficha_animal(request, animal_id):
    animal = get_object_or_404(
        Animal.objects.select_related("raza"),
        pk=animal_id,
    )
    estado_animal = Estado.objects.filter(
        pk=animal.id_estado,
        tipo_estado="Animal",
    ).first()
    rescate = (
        Rescate.objects.select_related(
            "id_estado",
            "rut_personal",
            "rut_personal__id_usuario",
        )
        .filter(pk=animal.id_rescate)
        .first()
    )
    vacunas_animal = (
        VacunaAnimal.objects.select_related("id_vacuna")
        .filter(id_animal=animal)
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

    session_user = request.session.get("refugio_usuario", {})
    puede_editar = bool(
        session_user.get("id")
        and Personal.objects.filter(
            id_usuario__supabase_uid=session_user["id"]
        ).exists()
    )

    return render(
        request,
        "ficha_animal.html",
        {
            "animal": animal,
            "estado_animal": estado_animal,
            "rescate": rescate,
            "vacunas_animal": vacunas_animal,
            "personal_nombre": personal_nombre,
            "puede_editar": puede_editar,
        },
    )


def gestion_salud_animal(request):
    if request.method not in {"GET", "POST"}:
        return render(
            request,
            "salud_animales.html",
            {"error": "Método no permitido."},
            status=405,
        )

    session_user = request.session.get("refugio_usuario")
    if not session_user:
        messages.info(request, "Inicia sesión con una cuenta del personal para continuar.")
        return redirect("login_usuario")

    supabase_uid = session_user.get("id")
    if not supabase_uid:
        return render(
            request,
            "salud_animales.html",
            {"error": "No pudimos verificar tu cuenta. Vuelve a iniciar sesión."},
            status=403,
        )

    try:
        personal = Personal.objects.select_related("id_usuario").get(
            id_usuario__supabase_uid=supabase_uid
        )
    except Personal.DoesNotExist:
        return render(
            request,
            "salud_animales.html",
            {"error": "Esta sección está disponible para el personal del refugio."},
            status=403,
        )

    veterinario = None
    if personal.rol == "veterinario":
        veterinario = Veterinario.objects.filter(
            rut_personal_id=personal.pk
        ).first()

    animales = Animal.objects.select_related("raza").order_by("nombre", "id_animal")
    animal_id = (
        request.POST.get("animal_id")
        if request.method == "POST"
        else request.GET.get("animal")
    )
    animal = None
    if animal_id:
        animal = get_object_or_404(animales, pk=animal_id)

    evaluaciones = EvaluacionAnimal.objects.none()
    tratamientos = Tratamiento.objects.none()
    ultima_evaluacion = None
    if animal:
        evaluaciones = (
            EvaluacionAnimal.objects.select_related(
                "rut_personal__rut_personal__id_usuario"
            )
            .filter(id_animal=animal)
        )
        ultima_evaluacion = evaluaciones.first()
        tratamientos = (
            Tratamiento.objects.select_related(
                "id_estado",
                "rut_personal__rut_personal__id_usuario",
            )
            .filter(id_animal=animal)
        )

    puede_registrar = veterinario is not None
    puede_registrar_tratamiento = bool(
        puede_registrar
        and ultima_evaluacion
        and ultima_evaluacion.necesita_tratamiento
    )
    evaluation_form = EvaluacionAnimalForm()
    treatment_form = TratamientoAnimalForm()
    error = None

    if request.method == "POST":
        if not puede_registrar:
            return render(
                request,
                "salud_animales.html",
                {
                    "error": (
                        "Solo un veterinario registrado puede añadir "
                        "evaluaciones o tratamientos."
                    ),
                    "animales": animales,
                    "animal": animal,
                },
                status=403,
            )
        if not animal:
            return render(
                request,
                "salud_animales.html",
                {
                    "error": "Selecciona un animal antes de registrar información.",
                    "animales": animales,
                },
                status=400,
            )

        action = request.POST.get("action")
        if action == "evaluacion":
            evaluation_form = EvaluacionAnimalForm(request.POST)
            if evaluation_form.is_valid():
                datos = evaluation_form.cleaned_data
                try:
                    EvaluacionAnimal.objects.create(
                        fecha=datos["fecha"],
                        estado_salud=datos["estado_salud"],
                        necesita_tratamiento=datos["necesita_tratamiento"],
                        observacion=datos["observacion"],
                        id_animal=animal,
                        rut_personal=veterinario,
                    )
                except DatabaseError:
                    logger.exception(
                        "Unable to save health evaluation for animal %s by veterinarian %s",
                        animal.pk,
                        personal.pk,
                    )
                    error = "No pudimos guardar la evaluación. Inténtalo nuevamente."
                else:
                    messages.success(request, "La evaluación se registró correctamente.")
                    return redirect(f"{request.path}?animal={animal.pk}")
        elif action == "tratamiento":
            treatment_form = TratamientoAnimalForm(request.POST)
            if not puede_registrar_tratamiento:
                error = (
                    "Para registrar un tratamiento, la evaluación más reciente "
                    "debe indicar que el animal lo necesita."
                )
            elif treatment_form.is_valid():
                datos = treatment_form.cleaned_data
                try:
                    Tratamiento.objects.create(
                        fecha_inicio=datos["fecha_inicio"],
                        fecha_termino=datos["fecha_termino"],
                        tipo_tratamiento=datos["tipo_tratamiento"],
                        detalle=datos["detalle"],
                        observacion=datos["observacion"] or None,
                        diagnostico=datos["diagnostico"],
                        costo=datos["costo"],
                        id_estado=datos["id_estado"],
                        rut_personal=veterinario,
                        id_animal=animal,
                    )
                except DatabaseError:
                    logger.exception(
                        "Unable to save treatment for animal %s by veterinarian %s",
                        animal.pk,
                        personal.pk,
                    )
                    error = "No pudimos guardar el tratamiento. Inténtalo nuevamente."
                else:
                    messages.success(request, "El tratamiento se registró correctamente.")
                    return redirect(f"{request.path}?animal={animal.pk}")
        else:
            error = "Selecciona una acción válida."

    status = 200
    if request.method == "POST" and (
        error
        or (
            request.POST.get("action") == "evaluacion"
            and not evaluation_form.is_valid()
        )
        or (
            request.POST.get("action") == "tratamiento"
            and not treatment_form.is_valid()
        )
    ):
        status = 400

    return render(
        request,
        "salud_animales.html",
        {
            "animales": animales,
            "animal": animal,
            "evaluaciones": evaluaciones,
            "tratamientos": tratamientos,
            "ultima_evaluacion": ultima_evaluacion,
            "puede_registrar": puede_registrar,
            "puede_registrar_tratamiento": puede_registrar_tratamiento,
            "evaluation_form": evaluation_form,
            "treatment_form": treatment_form,
            "error": error,
            "veterinario_sin_perfil": personal.rol == "veterinario" and not veterinario,
        },
        status=status,
    )


def gestion_vacunas(request):
    if request.method not in {"GET", "POST"}:
        return render(
            request,
            "vacunas_animales.html",
            {"error": "Método no permitido."},
            status=405,
        )

    session_user = request.session.get("refugio_usuario")
    if not session_user:
        messages.info(request, "Inicia sesión con una cuenta del personal para continuar.")
        return redirect("login_usuario")

    supabase_uid = session_user.get("id")
    if not supabase_uid:
        return render(
            request,
            "vacunas_animales.html",
            {"error": "No pudimos verificar tu cuenta. Vuelve a iniciar sesión."},
            status=403,
        )

    try:
        personal = Personal.objects.get(id_usuario__supabase_uid=supabase_uid)
    except Personal.DoesNotExist:
        return render(
            request,
            "vacunas_animales.html",
            {"error": "Esta sección está disponible para el personal del refugio."},
            status=403,
        )

    veterinario = None
    if personal.rol == "veterinario":
        veterinario = Veterinario.objects.filter(
            rut_personal_id=personal.pk
        ).first()

    animales = Animal.objects.select_related("raza").order_by("nombre", "id_animal")
    animal_id = (
        request.POST.get("animal_id")
        if request.method == "POST"
        else request.GET.get("animal")
    )
    animal = None
    if animal_id:
        animal = get_object_or_404(animales, pk=animal_id)

    vacunas_animal = VacunaAnimal.objects.none()
    if animal:
        vacunas_animal = (
            VacunaAnimal.objects.select_related(
                "id_vacuna",
                "id_animal",
            )
            .filter(id_animal=animal)
        )

    puede_registrar = veterinario is not None
    vacuna_form = VacunaAnimalForm()
    error = None

    if request.method == "POST":
        if not puede_registrar:
            return render(
                request,
                "vacunas_animales.html",
                {
                    "error": (
                        "Solo un veterinario registrado puede añadir "
                        "vacunas al historial."
                    ),
                    "animales": animales,
                    "animal": animal,
                },
                status=403,
            )
        if not animal:
            return render(
                request,
                "vacunas_animales.html",
                {
                    "error": "Selecciona un animal antes de registrar una vacuna.",
                    "animales": animales,
                },
                status=400,
            )

        vacuna_form = VacunaAnimalForm(request.POST)
        if vacuna_form.is_valid():
            datos = vacuna_form.cleaned_data
            try:
                VacunaAnimal.objects.create(
                    fecha_aplicacion=datos["fecha_aplicacion"],
                    fecha_prox_dosis=datos["fecha_prox_dosis"],
                    aplicada=datos["aplicada"],
                    observacion=datos["observacion"],
                    id_animal=animal,
                    id_vacuna=datos["id_vacuna"],
                )
            except DatabaseError:
                logger.exception(
                    "Unable to save vaccine record for animal %s by veterinarian %s",
                    animal.pk,
                    personal.pk,
                )
                error = "No pudimos guardar la vacuna. Revisa los datos e inténtalo nuevamente."
            else:
                messages.success(request, "La vacuna se registró correctamente.")
                return redirect(f"{request.path}?animal={animal.pk}")

    status = 400 if request.method == "POST" and (
        error or not vacuna_form.is_valid()
    ) else 200
    return render(
        request,
        "vacunas_animales.html",
        {
            "animales": animales,
            "animal": animal,
            "vacunas_animal": vacunas_animal,
            "puede_registrar": puede_registrar,
            "vacuna_form": vacuna_form,
            "error": error,
            "veterinario_sin_perfil": personal.rol == "veterinario" and not veterinario,
        },
        status=status,
    )


def editar_animal(request, animal_id):
    session_user = request.session.get("refugio_usuario")
    if not session_user:
        messages.info(request, "Inicia sesión con una cuenta del personal para continuar.")
        return redirect("login_usuario")

    supabase_uid = session_user.get("id")
    if not supabase_uid:
        return render(
            request,
            "editar_animal.html",
            {"error": "No pudimos verificar tu cuenta. Vuelve a iniciar sesión."},
            status=403,
        )

    try:
        personal = Personal.objects.get(id_usuario__supabase_uid=supabase_uid)
    except Personal.DoesNotExist:
        return render(
            request,
            "editar_animal.html",
            {
                "error": (
                    "La edición está disponible únicamente para integrantes "
                    "del personal del refugio."
                )
            },
            status=403,
        )

    animal = get_object_or_404(Animal, pk=animal_id)
    if request.method == "GET":
        form = EditarAnimalForm(instance=animal)
        return render(
            request,
            "editar_animal.html",
            {"animal": animal, "form": form},
        )
    if request.method != "POST":
        return render(
            request,
            "editar_animal.html",
            {
                "animal": animal,
                "form": EditarAnimalForm(instance=animal),
                "error": "Este formulario solo acepta solicitudes POST.",
            },
            status=405,
        )

    form = EditarAnimalForm(request.POST, request.FILES, instance=animal)
    if not form.is_valid():
        return render(
            request,
            "editar_animal.html",
            {"animal": animal, "form": form},
            status=400,
        )

    uploaded_image = form.cleaned_data["foto"]
    uploaded_image_path = None
    bucket = None
    if uploaded_image:
        if supabase_storage is None:
            return render(
                request,
                "editar_animal.html",
                {
                    "animal": animal,
                    "form": form,
                    "error": (
                        "No está disponible el cambio de foto en este momento. "
                        "Inténtalo más tarde."
                    ),
                },
                status=503,
            )

        image_extensions = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}
        image_content_types = {
            "JPEG": "image/jpeg",
            "PNG": "image/png",
            "WEBP": "image/webp",
        }
        image_format = uploaded_image.image.format
        uploaded_image_path = (
            f"{session_user['id']}/{uuid4().hex}."
            f"{image_extensions[image_format]}"
        )
        bucket = supabase_storage.storage.from_("animales")
        uploaded_image.seek(0)
        try:
            bucket.upload(
                uploaded_image_path,
                uploaded_image.read(),
                {
                    "content-type": image_content_types[image_format],
                    "upsert": "false",
                },
            )
        except Exception:
            logger.exception(
                "Unable to upload replacement image for animal %s",
                animal.pk,
            )
            return render(
                request,
                "editar_animal.html",
                {
                    "animal": animal,
                    "form": form,
                    "error": (
                        "No pudimos subir la nueva foto. Revisa el archivo "
                        "e inténtalo de nuevo."
                    ),
                },
                status=502,
            )

    try:
        with transaction.atomic():
            animal = form.save(commit=False)
            if uploaded_image_path:
                animal.foto_url = bucket.get_public_url(uploaded_image_path)
            animal.save()
    except DatabaseError:
        logger.exception(
            "Unable to update animal %s by personal %s",
            animal.pk,
            personal.rut_personal,
        )
        if uploaded_image_path:
            try:
                bucket.remove([uploaded_image_path])
            except Exception:
                logger.exception(
                    "Unable to remove orphaned replacement image for animal %s",
                    animal.pk,
                )
        return render(
            request,
            "editar_animal.html",
            {
                "animal": animal,
                "form": form,
                "error": "No pudimos guardar los cambios. Revisa los datos e inténtalo de nuevo.",
            },
            status=500,
        )

    messages.success(request, "Los datos del animal se actualizaron correctamente.")
    return redirect("ficha_animal", animal_id=animal.pk)


def _registro_animal_context(form, error=None):
    return {
        "form": form,
        "error": error,
        "animal_fields": [
            form[name]
            for name in (
                "nombre",
                "edad_aprox",
                "sexo",
                "peso",
                "descripcion",
                "lugar_rescate",
                "condicion",
                "especie",
                "microchip",
                "foto",
                "fecha_ingreso",
                "comportamiento",
                "raza",
                "estado_animal",
            )
        ],
        "rescue_fields": [
            form[name]
            for name in (
                "fecha_rescate",
                "descripcion_rescate",
                "condicion_inicial",
                "observacion_rescate",
                "estado_rescate",
            )
        ],
    }


def registro_animal(request):
    session_user = request.session.get("refugio_usuario")
    if not session_user:
        messages.info(request, "Inicia sesión con una cuenta del personal para continuar.")
        return redirect("login_usuario")

    supabase_uid = session_user.get("id")
    if not supabase_uid:
        return render(
            request,
            "registro_animal.html",
            {"error": "No pudimos verificar tu cuenta. Vuelve a iniciar sesión."},
            status=403,
        )

    try:
        personal = Personal.objects.get(id_usuario__supabase_uid=supabase_uid)
    except Personal.DoesNotExist:
        return render(
            request,
            "registro_animal.html",
            {
                "error": (
                    "Esta función está disponible únicamente para integrantes "
                    "del personal del refugio."
                )
            },
            status=403,
        )

    if request.method == "GET":
        return render(
            request,
            "registro_animal.html",
            _registro_animal_context(RegistroAnimalForm()),
        )
    if request.method != "POST":
        return render(
            request,
            "registro_animal.html",
            _registro_animal_context(
                RegistroAnimalForm(),
                "Este formulario solo acepta solicitudes POST.",
            ),
            status=405,
        )

    form = RegistroAnimalForm(request.POST, request.FILES)
    if not form.is_valid():
        return render(
            request,
            "registro_animal.html",
            _registro_animal_context(form),
            status=400,
        )

    datos = form.cleaned_data
    foto_url = None
    uploaded_image = datos["foto"]
    uploaded_image_path = None
    if uploaded_image:
        if supabase_storage is None:
            return render(
                request,
                "registro_animal.html",
                _registro_animal_context(
                    form,
                    (
                        "La carga de fotos no está disponible en este momento. "
                        "Inténtalo más tarde."
                    ),
                ),
                status=503,
            )

        image_extensions = {
            "JPEG": "jpg",
            "PNG": "png",
            "WEBP": "webp",
        }
        image_content_types = {
            "JPEG": "image/jpeg",
            "PNG": "image/png",
            "WEBP": "image/webp",
        }
        image_format = uploaded_image.image.format
        uploaded_image_path = (
            f"{session_user['id']}/{uuid4().hex}."
            f"{image_extensions[image_format]}"
        )
        uploaded_image.seek(0)
        bucket = supabase_storage.storage.from_("animales")
        try:
            bucket.upload(
                uploaded_image_path,
                uploaded_image.read(),
                {
                    "content-type": image_content_types[image_format],
                    "upsert": "false",
                },
            )
            foto_url = bucket.get_public_url(uploaded_image_path)
        except Exception:
            logger.exception(
                "Unable to upload animal image to storage path %s",
                uploaded_image_path,
            )
            try:
                bucket.remove([uploaded_image_path])
            except Exception:
                logger.exception(
                    "Unable to clean up failed animal image upload at path %s",
                    uploaded_image_path,
                )
            return render(
                request,
                "registro_animal.html",
                _registro_animal_context(
                    form,
                    (
                        "No pudimos subir la foto. Revisa el archivo e "
                        "inténtalo de nuevo."
                    ),
                ),
                status=502,
            )

    try:
        with transaction.atomic():
            rescate = Rescate.objects.create(
                fecha_rescate=datos["fecha_rescate"],
                lugar_rescate=datos["lugar_rescate"],
                descripcion=datos["descripcion_rescate"],
                condicion_inicial=datos["condicion_inicial"],
                observacion=datos["observacion_rescate"] or None,
                id_estado=datos["estado_rescate"],
                rut_personal=personal,
            )
            Animal.objects.create(
                nombre=datos["nombre"] or None,
                edad_aprox=datos["edad_aprox"],
                sexo=datos["sexo"],
                peso=datos["peso"],
                descripcion=datos["descripcion"],
                lugar_rescate=datos["lugar_rescate"],
                condicion=datos["condicion"],
                especie=datos["especie"],
                microchip=datos["microchip"],
                foto_url=foto_url,
                fecha_ingreso=datos["fecha_ingreso"],
                fecha_salida=None,
                comportamiento=datos["comportamiento"],
                raza=datos["raza"],
                id_rescate=rescate.pk,
                id_estado=datos["estado_animal"].pk,
            )
    except DatabaseError:
        logger.exception(
            "Unable to save animal and rescue for personal %s",
            personal.rut_personal,
        )
        if uploaded_image_path:
            try:
                supabase_storage.storage.from_("animales").remove(
                    [uploaded_image_path]
                )
            except Exception:
                logger.exception(
                    "Unable to remove orphaned animal image at path %s",
                    uploaded_image_path,
                )
        return render(
            request,
            "registro_animal.html",
            _registro_animal_context(
                form,
                (
                    "No pudimos guardar el animal y su rescate. "
                    "Revisa los datos e inténtalo de nuevo."
                ),
            ),
            status=500,
        )

    messages.success(request, "El animal y su rescate se registraron correctamente.")
    return redirect("inicio_refugio")


def login_usuario(request):
    if request.method == "GET":
        return render(
            request,
            "login.html",
            {"next": request.GET.get("next", "")},
        )
    if request.method != "POST":
        return render(
            request,
            "login.html",
            {
                "error": "Este formulario solo acepta solicitudes POST.",
                "next": request.POST.get("next", ""),
            },
            status=405,
        )

    next_url = request.POST.get("next", "")
    email = request.POST.get("email", "").strip().lower()
    password = request.POST.get("password", "")
    if not email or not password:
        return render(
            request,
            "login.html",
            {
                "error": "Ingresa tu correo electrónico y contraseña.",
                "email": email,
                "next": next_url,
            },
            status=400,
        )
    if supabase is None:
        return render(
            request,
            "login.html",
            {
                "error": (
                    "El inicio de sesión no está disponible en este momento. "
                    "Inténtalo más tarde."
                ),
                "next": next_url,
            },
            status=503,
        )

    try:
        auth_response = supabase.auth.sign_in_with_password(
            {"email": email, "password": password}
        )
    except Exception:
        return render(
            request,
            "login.html",
            {
                "error": (
                    "No pudimos iniciar sesión. Revisa tu correo y contraseña "
                    "e inténtalo de nuevo."
                ),
                "email": email,
                "next": next_url,
            },
            status=401,
        )

    try:
        usuario = Usuario.objects.get(supabase_uid=auth_response.user.id)
    except Usuario.DoesNotExist:
        usuario = Usuario.objects.filter(
            correo__iexact=email,
            supabase_uid__isnull=True,
        ).first()
        if usuario is None:
            return render(
                request,
                "login.html",
                {
                    "error": (
                        "No encontramos los datos de tu cuenta. "
                        "Contacta al equipo del refugio."
                    ),
                    "email": email,
                    "next": next_url,
                },
                status=404,
            )

        usuario.supabase_uid = auth_response.user.id
        usuario.save(update_fields=["supabase_uid"])
        usuario = Usuario.objects.get(pk=usuario.pk)

    personal = (
        Personal.objects.filter(id_usuario=usuario)
        .order_by("rut_personal")
        .first()
    )

    nombre = " ".join(
        parte
        for parte in (
            usuario.p_nombre,
            usuario.s_nombre,
            usuario.ap_paterno,
            usuario.ap_materno,
        )
        if parte
    )
    request.session["refugio_usuario"] = {
        "id": str(usuario.supabase_uid),
        "nombre": nombre,
        "correo": usuario.correo,
        "rol": personal.rol if personal else None,
    }
    request.session["supabase_access_token"] = auth_response.session.access_token
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(next_url)
    return redirect("inicio_refugio")


def registro_usuario(request):
    if request.method == "GET":
        return render(request, "registro.html", {"form": RegistroUsuarioForm()})
    if request.method != "POST":
        return render(
            request,
            "registro.html",
            {"form": RegistroUsuarioForm(), "error": "Método no permitido."},
            status=405,
        )

    form = RegistroUsuarioForm(request.POST)
    if not form.is_valid():
        return render(request, "registro.html", {"form": form}, status=400)
    if supabase is None:
        return render(
            request,
            "registro.html",
            {
                "form": form,
                "error": (
                    "El registro no está disponible en este momento. "
                    "Inténtalo más tarde."
                ),
            },
            status=503,
        )

    datos = form.cleaned_data
    correo = datos["correo"]
    existing_user = Usuario.objects.filter(correo__iexact=correo).first()
    if existing_user:
        if existing_user.supabase_uid is None:
            form.add_error(
                "correo",
                (
                    "Ya comenzaste el registro con este correo. Si confirmaste "
                    "tu dirección, intenta iniciar sesión. Si no, revisa tu correo."
                ),
            )
        else:
            form.add_error(
                "correo",
                "Ya existe una cuenta con este correo. Inicia sesión o usa otro.",
            )
        return render(request, "registro.html", {"form": form}, status=400)

    try:
        auth_response = supabase.auth.sign_up(
            {
                "email": correo,
                "password": datos["password"],
                "options": {
                    "data": {
                        "p_nombre": datos["p_nombre"],
                        "s_nombre": datos["s_nombre"],
                        "ap_paterno": datos["ap_paterno"],
                        "ap_materno": datos["ap_materno"],
                        "genero": datos["genero"],
                        "fecha_nacimiento": datos["fecha_nacimiento"].isoformat(),
                        "telefono": datos["telefono"] or None,
                    }
                },
            }
        )
    except Exception as error:
        error_code = getattr(error, "code", None)
        error_status = getattr(error, "status", None)
        logger.warning(
            "Supabase sign-up failed (type=%s, status=%s, code=%s)",
            type(error).__name__,
            error_status,
            error_code,
        )
        if error_code in {"user_already_exists", "email_exists"}:
            form.add_error(
                "correo",
                (
                    "Ya existe una cuenta con este correo. "
                    "Inicia sesión o usa otro."
                ),
            )
            return render(request, "registro.html", {"form": form}, status=400)

        if error_status == 429:
            return render(
                request,
                "registro.html",
                {
                    "form": form,
                    "error": (
                        "Por el momento no podemos enviar más correos de registro. "
                        "Inténtalo más tarde."
                    ),
                },
                status=429,
            )

        if isinstance(error, ReadTimeout):
            return render(
                request,
                "registro.html",
                {
                    "form": form,
                    "error": (
                        "No pudimos confirmar tu registro. Es posible que tu "
                        "cuenta se haya creado. Revisa tu correo o intenta "
                        "iniciar sesión antes de registrarte otra vez."
                    ),
                },
                status=504,
            )

        return render(
            request,
            "registro.html",
            {
                "form": form,
                "error": (
                    "No pudimos crear tu cuenta. Revisa los datos e inténtalo "
                    "de nuevo."
                ),
            },
            status=400,
        )

    if auth_response.user is None:
        return render(
            request,
            "registro.html",
            {
                "form": form,
                "error": (
                    "No pudimos confirmar la creación de tu cuenta. "
                    "Espera un momento antes de volver a intentarlo."
                ),
            },
            status=502,
        )

    usuario = Usuario.objects.filter(
        supabase_uid=auth_response.user.id
    ).first()
    expected_profile = {
        "p_nombre": datos["p_nombre"],
        "s_nombre": datos["s_nombre"],
        "ap_paterno": datos["ap_paterno"],
        "ap_materno": datos["ap_materno"],
        "correo": correo,
        "genero": datos["genero"],
        "fecha_nacimiento": datos["fecha_nacimiento"],
    }
    if (
        usuario is None
        or any(
            getattr(usuario, field) != value
            for field, value in expected_profile.items()
        )
    ):
        logger.error(
            "Supabase account %s was created but its usuario profile is missing "
            "or does not match the submitted registration data.",
            auth_response.user.id,
        )
        return render(
            request,
            "registro.html",
            {
                "form": form,
                "error": (
                    "Tu cuenta se creó, pero no pudimos guardar correctamente "
                    "tus datos. Contacta al equipo del refugio antes de volver "
                    "a registrarte."
                ),
            },
            status=502,
        )

    messages.success(
        request,
        (
            "Tu cuenta fue creada. Si recibes un correo de confirmación, "
            "ábrelo antes de iniciar sesión."
        ),
    )
    return redirect("login_usuario")


@require_POST
def logout_usuario(request):
    request.session.pop("refugio_usuario", None)
    request.session.pop("supabase_access_token", None)
    messages.success(request, "Cerraste sesión correctamente.")
    return redirect("inicio_refugio")


@csrf_exempt
def login_personal(request):
    if request.method != "POST":
        response = JsonResponse(
            {"error": "Este endpoint solo acepta solicitudes POST."},
            status=405,
        )
        response["Allow"] = "POST"
        return response

    try:
        credentials = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse(
            {"error": "El cuerpo debe contener JSON válido."},
            status=400,
        )

    if not isinstance(credentials, dict):
        return JsonResponse({"error": "El cuerpo JSON debe ser un objeto."}, status=400)

    email = credentials.get("email")
    password = credentials.get("password")
    if (
        not isinstance(email, str)
        or not email
        or not isinstance(password, str)
        or not password
    ):
        return JsonResponse(
            {"error": "Se requieren los campos 'email' y 'password'."},
            status=400,
        )

    if supabase is None:
        return JsonResponse(
            {"error": "La autenticación no está disponible en este momento."},
            status=503,
        )

    try:
        auth_response = supabase.auth.sign_in_with_password(
            {"email": email, "password": password}
        )
    except Exception:
        return JsonResponse(
            {"error": "No se pudo autenticar con esas credenciales."},
            status=401,
        )

    try:
        usuario = Usuario.objects.get(supabase_uid=auth_response.user.id)
    except Usuario.DoesNotExist:
        return JsonResponse(
            {"error": "El usuario no existe en la base de datos local."},
            status=404,
        )

    personal = (
        Personal.objects.filter(id_usuario=usuario)
        .order_by("rut_personal")
        .first()
    )

    nombre = " ".join(
        parte
        for parte in (
            usuario.p_nombre,
            usuario.s_nombre,
            usuario.ap_paterno,
            usuario.ap_materno,
        )
        if parte
    )
    return JsonResponse(
        {
            "access_token": auth_response.session.access_token,
            "usuario": {
                "nombre": nombre,
                "correo": usuario.correo,
            },
            "personal": {
                "rol": personal.rol,
                "rut_personal": personal.rut_personal,
            }
            if personal
            else None,
        }
    )
