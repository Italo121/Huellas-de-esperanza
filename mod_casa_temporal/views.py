# Create your views here.
import logging
from pathlib import PurePosixPath
from uuid import uuid4

from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.db import DatabaseError, transaction
from django.db.models import Count, Prefetch, Q
from django.shortcuts import redirect, render, resolve_url
from django.urls import reverse
from django.utils import timezone

from mod_refugio.models import Animal, Estado, Personal, Usuario
from mod_refugio.supabase_client import supabase_storage

from .forms import (
    EVIDENCE_FILE_TYPES,
    GestionHogaresTemporalesForm,
    SolicitudHogarTemporalForm,
)
from .models import CasaTemporal, HogarAnimal, SolicitudHogarTemporal

logger = logging.getLogger(__name__)


def _remove_evidence_uploads(bucket, uploaded_paths, user_pk):
    if not uploaded_paths:
        return
    try:
        bucket.remove(uploaded_paths)
    except Exception:
        logger.exception(
            "Unable to clean up temporary-home evidence files for user %s",
            user_pk,
        )


def mis_hogares_temporales(request):
    session_user = request.session.get("refugio_usuario")
    if not session_user:
        messages.info(
            request,
            "Inicia sesión con tu cuenta para consultar tus hogares temporales.",
        )
        return redirect_to_login(
            request.get_full_path(),
            login_url=resolve_url("login_usuario"),
        )

    supabase_uid = session_user.get("id")
    if not supabase_uid:
        return render(
            request,
            "mis_hogares_temporales.html",
            {"error": "No pudimos verificar tu cuenta. Inicia sesión nuevamente."},
            status=403,
        )

    try:
        usuario = Usuario.objects.get(supabase_uid=supabase_uid)
    except Usuario.DoesNotExist:
        return render(
            request,
            "mis_hogares_temporales.html",
            {"error": "No encontramos los datos asociados a tu cuenta."},
            status=403,
        )

    asignaciones_activas = (
        HogarAnimal.objects.filter(fecha_salida__isnull=True)
        .select_related("id_animal")
        .order_by("-fecha_ingreso", "id_asignacion")
    )
    hogares = (
        CasaTemporal.objects.filter(id_usuario=usuario)
        .select_related("id_estado")
        .prefetch_related(
            Prefetch(
                "asignaciones_animales",
                queryset=asignaciones_activas,
                to_attr="animales_actuales",
            )
        )
        .order_by("-fecha_ingreso", "-id_casa")
    )
    return render(
        request,
        "mis_hogares_temporales.html",
        {"hogares": hogares},
    )


def gestion_hogares_temporales(request):
    template_name = "gestion_hogares_temporales.html"
    if request.method not in {"GET", "POST"}:
        response = render(
            request,
            template_name,
            {"error": "Método no permitido."},
            status=405,
        )
        response["Allow"] = "GET, POST"
        return response

    session_user = request.session.get("refugio_usuario")
    if not session_user:
        messages.info(
            request,
            "Inicia sesión con una cuenta del personal para continuar.",
        )
        return redirect_to_login(
            request.get_full_path(),
            login_url=resolve_url("login_usuario"),
        )

    supabase_uid = session_user.get("id")
    if not supabase_uid:
        return render(
            request,
            template_name,
            {"error": "No pudimos verificar tu cuenta. Inicia sesión nuevamente."},
            status=403,
        )

    try:
        personal = Personal.objects.get(id_usuario__supabase_uid=supabase_uid)
    except Personal.DoesNotExist:
        return render(
            request,
            template_name,
            {"error": "Esta sección está disponible para el personal activo del refugio."},
            status=403,
        )

    personal_activo = Personal.objects.filter(
        pk=personal.pk,
        id_estado__tipo_estado="Personal",
        id_estado__nombre="Activo",
    ).exists()
    if not personal_activo:
        return render(
            request,
            template_name,
            {"error": "Esta sección está disponible para el personal activo del refugio."},
            status=403,
        )

    hogares_activos = (
        CasaTemporal.objects.filter(
            id_estado__tipo_estado="Solicitud",
            id_estado__nombre="Aprobada",
        )
        .select_related("id_estado")
        .annotate(
            animales_activos=Count(
                "asignaciones_animales",
                filter=Q(asignaciones_animales__fecha_salida__isnull=True),
            )
        )
        .order_by("poblacion", "id_casa")
    )
    action = request.POST.get("action") if request.method == "POST" else None
    casa_id = (
        request.POST.get("casa_id")
        if request.method == "POST"
        else request.GET.get("casa")
    )
    hogar_seleccionado = hogares_activos.filter(pk=casa_id).first() if casa_id else None
    form = GestionHogaresTemporalesForm(
        request.POST if action == "asignar_animal" else None
    )
    error = None
    status = 200
    if request.method == "POST":
        if action not in {"asignar_animal", "retirar_animal", "desactivar_hogar"}:
            error = "Acción no válida."
            status = 400
        elif not casa_id:
            error = "Selecciona un hogar temporal para continuar."
            status = 400
        elif action == "asignar_animal" and not form.is_valid():
            error = "Revisa los datos del formulario."
            status = 400
        else:
            try:
                with transaction.atomic():
                    casa = CasaTemporal.objects.select_for_update().get(
                        pk=casa_id,
                        id_estado__tipo_estado="Solicitud",
                        id_estado__nombre="Aprobada",
                    )
                    if action == "retirar_animal":
                        asignacion_id = request.POST.get("asignacion_id")
                        if not asignacion_id:
                            error = "No se identificó la asignación que quieres cerrar."
                            status = 400
                        else:
                            asignacion = HogarAnimal.objects.select_for_update().get(
                                pk=asignacion_id,
                                id_casa=casa,
                                fecha_salida__isnull=True,
                            )
                            asignacion.fecha_salida = timezone.localdate()
                            asignacion.save(update_fields=("fecha_salida",))
                    elif action == "desactivar_hogar":
                        if HogarAnimal.objects.filter(
                            id_casa=casa,
                            fecha_salida__isnull=True,
                        ).exists():
                            error = (
                                "No se puede desactivar el hogar mientras tenga "
                                "animales asignados. Registra primero su salida."
                            )
                            status = 400
                        else:
                            estado_inactivo, _ = Estado.objects.get_or_create(
                                tipo_estado="Casa temporal",
                                nombre="Inactivo",
                            )
                            casa.id_estado = estado_inactivo
                            casa.save(update_fields=("id_estado",))
                    else:
                        datos = form.cleaned_data
                        animal = Animal.objects.select_for_update().get(
                            pk=datos["id_animal"].pk,
                            fecha_salida__isnull=True,
                        )
                        if HogarAnimal.objects.filter(
                            id_animal=animal,
                            fecha_salida__isnull=True,
                        ).exists():
                            error = "Este animal ya tiene un hogar temporal asignado."
                            status = 400
                        else:
                            HogarAnimal.objects.create(
                                fecha_ingreso=timezone.localdate(),
                                id_casa=casa,
                                id_animal=animal,
                            )
            except DatabaseError:
                logger.exception(
                    "Unable to manage temporary home %s action %s by staff %s",
                    casa_id,
                    action,
                    personal.pk,
                )
                error = "No pudimos guardar los cambios. Inténtalo nuevamente."
                status = 500
            except (Animal.DoesNotExist, CasaTemporal.DoesNotExist):
                error = (
                    "El hogar o el animal ya no está disponible. "
                    "Actualiza la página e inténtalo nuevamente."
                )
                status = 400
            except HogarAnimal.DoesNotExist:
                error = "La asignación ya no está activa en este hogar."
                status = 400

            if error is None:
                if action == "retirar_animal":
                    success_message = "La salida del animal quedó registrada correctamente."
                elif action == "desactivar_hogar":
                    success_message = "El hogar temporal fue marcado como inactivo."
                    casa_id = None
                else:
                    success_message = "El animal fue asignado al hogar temporal correctamente."
                messages.success(
                    request,
                    success_message,
                )
                if casa_id:
                    return redirect(
                        f"{reverse('mod_casa_temporal:gestion_hogares_temporales')}?casa={casa_id}"
                    )
                return redirect(
                    "mod_casa_temporal:gestion_hogares_temporales"
                )

    asignaciones_activas = (
        HogarAnimal.objects.all()
        .select_related("id_animal")
        .order_by("-fecha_ingreso", "id_asignacion")
    )
    asignaciones_hogar = []
    if hogar_seleccionado:
        asignaciones_hogar = list(
            asignaciones_activas.filter(id_casa=hogar_seleccionado)
        )
    return render(
        request,
        template_name,
        {
            "form": form,
            "error": error,
            "personal": personal,
            "hogares_activos": hogares_activos,
            "hogar_seleccionado": hogar_seleccionado,
            "asignaciones_hogar": asignaciones_hogar,
        },
        status=status,
    )


asignar_animal_hogar = gestion_hogares_temporales


def hogares_disponibles(request):
    hogares = (
        CasaTemporal.objects.filter(
            id_estado__tipo_estado="Solicitud",
            id_estado__nombre="Aprobada",
        )
        .values(
            "id_casa",
            "cant_persona",
            "cant_habitacion",
            "patio",
            "metro_c",
        )
        .annotate(
            animales_acogidos=Count(
                "asignaciones_animales",
                filter=Q(asignaciones_animales__fecha_salida__isnull=True),
            )
        )
        .order_by("id_casa")
    )
    hogares_publicos = [
        {
            "numero": index,
            "cant_persona": hogar["cant_persona"],
            "cant_habitacion": hogar["cant_habitacion"],
            "patio": hogar["patio"],
            "metro_c": hogar["metro_c"],
            "animales_acogidos": hogar["animales_acogidos"],
        }
        for index, hogar in enumerate(hogares, start=1)
    ]
    return render(
        request,
        "hogares_disponibles.html",
        {"hogares": hogares_publicos},
    )


def solicitar_hogar_temporal(request):
    template_name = "solicitud_hogar_temporal.html"
    if request.method not in {"GET", "POST"}:
        response = render(
            request,
            template_name,
            {"error": "Método no permitido."},
            status=405,
        )
        response["Allow"] = "GET, POST"
        return response

    session_user = request.session.get("refugio_usuario")
    if not session_user:
        messages.info(
            request,
            "Inicia sesión con tu cuenta para postular como hogar temporal.",
        )
        return redirect_to_login(
            request.get_full_path(),
            login_url=resolve_url("login_usuario"),
        )

    supabase_uid = session_user.get("id")
    if not supabase_uid:
        return render(
            request,
            template_name,
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
            template_name,
            {
                "error": (
                    "No encontramos los datos asociados a tu cuenta. "
                    "Inicia sesión nuevamente o contacta al refugio."
                )
            },
            status=403,
        )

    solicitud_pendiente = (
        SolicitudHogarTemporal.objects.filter(
            id_casa__id_usuario=usuario,
            id_estado__tipo_estado="Solicitud",
            id_estado__nombre="Pendiente",
        )
        .select_related("id_estado", "id_casa")
        .order_by("-fecha_solicitud", "-id_solicitud_hog")
        .first()
    )
    solicitud_usuario = (
        SolicitudHogarTemporal.objects.filter(id_casa__id_usuario=usuario)
        .select_related("id_estado", "id_casa")
        .order_by("-fecha_solicitud", "-id_solicitud_hog")
        .first()
    )
    form = SolicitudHogarTemporalForm()
    error = None
    response_status = 200

    if request.method == "POST" and solicitud_pendiente is None:
        form = SolicitudHogarTemporalForm(request.POST, request.FILES)
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
                    "Pending temporary-home application state is missing"
                )
            else:
                datos = form.cleaned_data
                evidencia = datos["evidencia"]
                archivos = datos["evidencia_archivos"]
                uploaded_paths = []
                bucket = None

                if archivos and supabase_storage is None:
                    error = (
                        "La carga de archivos no está disponible en este "
                        "momento. Inténtalo más tarde."
                    )
                    response_status = 503
                elif archivos:
                    lineas_archivos = []
                    try:
                        bucket = supabase_storage.storage.from_("Evidencias")
                        for archivo in archivos:
                            extension = PurePosixPath(
                                archivo.name.replace("\\", "/")
                            ).suffix.lower()
                            content_type = EVIDENCE_FILE_TYPES[extension][0]
                            ruta = f"{uuid4().hex}{extension}"
                            archivo.seek(0)
                            bucket.upload(
                                ruta,
                                archivo.read(),
                                {
                                    "content-type": content_type,
                                    "upsert": "false",
                                },
                            )
                            uploaded_paths.append(ruta)
                            url_archivo = bucket.get_public_url(ruta)
                            nombre_archivo = PurePosixPath(
                                archivo.name.replace("\\", "/")
                            ).name.replace("\r", "").replace("\n", "")
                            lineas_archivos.append(
                                f"- {nombre_archivo}: {url_archivo}"
                            )

                        separador = "\n\n----- Evidencias adjuntas -----\n"
                        if evidencia:
                            evidencia = f"{evidencia}{separador}"
                        else:
                            evidencia = "Evidencias adjuntas:\n"
                        evidencia += "\n".join(lineas_archivos)
                    except Exception:
                        logger.exception(
                            "Unable to upload temporary-home evidence files "
                            "for user %s",
                            usuario.pk,
                        )
                        _remove_evidence_uploads(
                            bucket,
                            uploaded_paths,
                            usuario.pk,
                        )
                        error = (
                            "No pudimos subir los archivos de evidencia. "
                            "Revisa los archivos e inténtalo nuevamente."
                        )
                        response_status = 502

                if error is None:
                    try:
                        with transaction.atomic():
                            casa = CasaTemporal.objects.create(
                                poblacion=datos["poblacion"],
                                calle=datos["calle"],
                                num_casa=datos["num_casa"],
                                cant_persona=datos["cant_persona"],
                                cant_habitacion=datos["cant_habitacion"],
                                patio=datos["patio"],
                                metro_c=datos["metro_c"],
                                evidencia=evidencia,
                                observacion=datos["observacion_casa"] or None,
                                fecha_ingreso=timezone.localdate(),
                                id_usuario=usuario,
                                id_estado=estado_pendiente,
                            )
                            SolicitudHogarTemporal.objects.create(
                                fecha_solicitud=timezone.localdate(),
                                motivo=datos["motivo"],
                                id_casa=casa,
                                id_estado=estado_pendiente,
                            )
                    except DatabaseError:
                        logger.exception(
                            "Unable to save temporary-home application for user %s",
                            usuario.pk,
                        )
                        _remove_evidence_uploads(
                            bucket,
                            uploaded_paths,
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
                            "Tu postulación como hogar temporal fue enviada correctamente.",
                        )
                        return redirect(
                            "mod_casa_temporal:solicitar_hogar_temporal"
                        )

    return render(
        request,
        template_name,
        {
            "usuario": usuario,
            "form": form,
            "error": error,
            "solicitud_pendiente": solicitud_pendiente,
            "solicitud_usuario": solicitud_usuario,
        },
        status=response_status,
    )
