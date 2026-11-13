import logging

from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import ValidationError
from django.db import DatabaseError, transaction
from django.db.models import Exists, OuterRef, Prefetch
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from mod_refugio.models import Estado, Personal, Usuario

from .forms import ComentarioForm, PublicacionForm
from .models import Comentario, Publicacion, PublicacionPersonal

logger = logging.getLogger(__name__)


TIPOS_PUBLICACION = tuple(
    (valor, etiqueta)
    for valor, etiqueta in PublicacionForm.base_fields["categoria"].choices
    if valor
)


def publicaciones(request):
    return _render_publicaciones(request)


def moderacion(request):
    error_response = _personal_de_sesion(request)
    if error_response is not None:
        return error_response

    try:
        tipo_seleccionado = request.GET.get("tipo", "").strip()
        tipos_validos = {valor for valor, _etiqueta in TIPOS_PUBLICACION}
        if tipo_seleccionado not in tipos_validos:
            tipo_seleccionado = ""

        publicaciones = Publicacion.objects.filter(
            id_estado__tipo_estado="Publicacion"
        )
        if tipo_seleccionado:
            publicaciones = publicaciones.filter(categoria=tipo_seleccionado)

        publicaciones = (
            publicaciones
            .select_related("id_estado")
            .prefetch_related(
                Prefetch(
                    "comentarios",
                    queryset=Comentario.objects.filter(
                        id_estado__tipo_estado="Comentario",
                    ).select_related("id_usuario", "id_estado"),
                )
            )
        )
        return render(
            request,
            "moderacion.html",
            {
                "publicaciones": publicaciones,
                "tipos_publicacion": TIPOS_PUBLICACION,
                "tipo_seleccionado": tipo_seleccionado,
            },
        )
    except DatabaseError:
        logger.exception("No se pudieron cargar publicaciones para moderar")
        return HttpResponse(
            "No fue posible cargar el contenido del foro.",
            status=503,
        )


def _render_publicaciones(request, publicacion_form=None):
    publicaciones = (
        Publicacion.objects.filter(
            id_estado__tipo_estado="Publicacion",
            id_estado__nombre="Publicada",
        )
        .annotate(
            es_publicacion_personal=Exists(
                PublicacionPersonal.objects.filter(
                    publicacion_id=OuterRef("pk"),
                )
            )
        )
        .select_related("id_estado")
        .prefetch_related(
            Prefetch(
                "comentarios",
                queryset=Comentario.objects.filter(
                    id_estado__tipo_estado="Comentario",
                    id_estado__nombre="Visible",
                ).select_related("id_usuario", "id_estado"),
            )
        )
        .all()
    )
    return render(
        request,
        "publicaciones.html",
        {
            "publicaciones": publicaciones,
            "publicacion_form": (
                publicacion_form if publicacion_form is not None else PublicacionForm()
            ),
            "usuario_conectado": _usuario_de_sesion(request),
        },
    )


@require_POST
def crear_publicacion(request):
    usuario = _usuario_de_sesion(request)
    if usuario is None:
        return _solicitar_inicio_sesion(request)

    form = PublicacionForm(request.POST)
    if form.is_valid():
        publicacion = form.save(commit=False)
        estado_publicada = _estado_foro("Publicacion", "Publicada")
        if estado_publicada is None:
            logger.error("Falta el estado Publicacion/Publicada en la base de datos")
            messages.error(request, "No se puede publicar en este momento.")
            return redirect("mod_foro:publicaciones")
        publicacion.fecha_publicacion = timezone.localdate()
        publicacion.id_estado = estado_publicada
        try:
            with transaction.atomic():
                publicacion.save()
                if Personal.objects.filter(id_usuario=usuario).exists():
                    PublicacionPersonal.objects.create(
                        publicacion=publicacion,
                        usuario=usuario,
                    )
        except DatabaseError:
            logger.exception("No se pudo guardar la publicación del foro")
            messages.error(request, "No se pudo publicar. Inténtalo nuevamente.")
        else:
            messages.success(request, "Tu publicación se compartió correctamente.")
    else:
        messages.error(
            request,
            "Revisa la categoría, el título, el contenido y la ubicación.",
        )
        return _render_publicaciones(request, form)
    return redirect("mod_foro:publicaciones")


@require_POST
def crear_comentario(request, publicacion_id):
    usuario = _usuario_de_sesion(request)
    if usuario is None:
        return _solicitar_inicio_sesion(request)

    publicacion = get_object_or_404(
        Publicacion,
        pk=publicacion_id,
        id_estado__tipo_estado="Publicacion",
        id_estado__nombre="Publicada",
    )
    form = ComentarioForm(request.POST)
    if form.is_valid():
        comentario = form.save(commit=False)
        estado_visible = _estado_foro("Comentario", "Visible")
        if estado_visible is None:
            logger.error("Falta el estado Comentario/Visible en la base de datos")
            messages.error(request, "No se puede comentar en este momento.")
            return redirect(f"{reverse('mod_foro:publicaciones')}#publicacion-{publicacion.pk}")
        comentario.id_usuario = usuario
        comentario.id_estado = estado_visible
        comentario.publicacion = publicacion
        comentario.fecha = timezone.localdate()
        try:
            comentario.save()
        except DatabaseError:
            logger.exception(
                "No se pudo guardar un comentario en la publicación %s",
                publicacion.pk,
            )
            messages.error(request, "No se pudo enviar el comentario. Inténtalo nuevamente.")
        else:
            messages.success(request, "Tu comentario se agregó correctamente.")
    else:
        messages.error(request, "El comentario no puede estar vacío ni superar 1000 caracteres.")
    return redirect(f"{reverse('mod_foro:publicaciones')}#publicacion-{publicacion.pk}")


@require_POST
def ocultar_publicacion(request, publicacion_id):
    return _cambiar_estado_foro(
        request,
        Publicacion,
        publicacion_id,
        "Publicacion",
        "Publicada",
        "Archivada",
        "La publicación se ocultó correctamente.",
        f"#publicacion-{publicacion_id}",
    )


@require_POST
def eliminar_publicacion(request, publicacion_id):
    error_response = _personal_de_sesion(request)
    if error_response is not None:
        return error_response

    try:
        with transaction.atomic():
            publicacion = get_object_or_404(
                Publicacion.objects.select_for_update(),
                pk=publicacion_id,
            )
            PublicacionPersonal.objects.filter(publicacion=publicacion).delete()
            Comentario.objects.filter(publicacion=publicacion).delete()
            publicacion.delete()
    except DatabaseError:
        logger.exception(
            "No se pudo eliminar la publicación %s y sus comentarios",
            publicacion_id,
        )
        messages.error(
            request,
            "No se pudo eliminar la publicación. Inténtalo nuevamente.",
        )
    else:
        messages.success(
            request,
            "La publicación y sus comentarios se eliminaron permanentemente.",
        )
    return redirect("mod_foro:moderacion")


@require_POST
def ocultar_comentario(request, comentario_id):
    return _cambiar_estado_foro(
        request,
        Comentario,
        comentario_id,
        "Comentario",
        "Visible",
        "Oculto (Moderado)",
        "El comentario se ocultó correctamente.",
    )


@require_POST
def mostrar_comentario(request, comentario_id):
    return _cambiar_estado_foro(
        request,
        Comentario,
        comentario_id,
        "Comentario",
        "Oculto (Moderado)",
        "Visible",
        "El comentario volvió a estar visible.",
    )


def _cambiar_estado_foro(
    request,
    modelo,
    objeto_id,
    tipo_estado,
    nombre_estado_actual,
    nombre_estado_nuevo,
    mensaje,
    ancla="",
):
    error_response = _personal_de_sesion(request)
    if error_response is not None:
        return error_response

    ruta_retorno = reverse("mod_foro:moderacion")

    try:
        estado = _estado_foro(tipo_estado, nombre_estado_nuevo)
    except DatabaseError:
        logger.exception(
            "No se pudo consultar el estado %s/%s del foro",
            tipo_estado,
            nombre_estado_nuevo,
        )
        messages.error(request, "No se pudo actualizar el estado en este momento.")
        return redirect(f"{ruta_retorno}{ancla}")
    if estado is None:
        logger.error(
            "Falta el estado %s/%s en la base de datos",
            tipo_estado,
            nombre_estado_nuevo,
        )
        messages.error(request, "No se pudo actualizar el estado en este momento.")
        return redirect(f"{ruta_retorno}{ancla}")

    try:
        filtros = {
            "pk": objeto_id,
            "id_estado__tipo_estado": tipo_estado,
            "id_estado__nombre": nombre_estado_actual,
        }
        objeto = get_object_or_404(modelo, **filtros)
        objeto.id_estado = estado
        objeto.save(update_fields=("id_estado",))
        if tipo_estado == "Comentario":
            ancla = f"#publicacion-{objeto.publicacion_id}"
    except DatabaseError:
        logger.exception(
            "No se pudo cambiar el estado %s/%s del foro",
            tipo_estado,
            objeto_id,
        )
        messages.error(request, "No se pudo actualizar. Inténtalo nuevamente.")
    else:
        messages.success(request, mensaje)
    return redirect(f"{ruta_retorno}{ancla}")


def _personal_de_sesion(request):
    session_user = request.session.get("refugio_usuario") or {}
    supabase_uid = session_user.get("id")
    if not supabase_uid:
        return _solicitar_inicio_sesion(request)

    try:
        es_personal = Personal.objects.filter(
            id_usuario__supabase_uid=supabase_uid,
        ).exists()
    except DatabaseError:
        logger.exception("No se pudo verificar el acceso de personal al foro")
        return HttpResponse(
            "No fue posible verificar los permisos del personal.",
            status=503,
        )
    if not es_personal:
        return HttpResponseForbidden(
            "Esta sección está disponible solo para el personal del refugio."
        )
    return None


def _usuario_de_sesion(request):
    session_user = request.session.get("refugio_usuario") or {}
    supabase_uid = session_user.get("id")
    if not supabase_uid:
        return None
    try:
        return Usuario.objects.filter(supabase_uid=supabase_uid).first()
    except (ValidationError, ValueError):
        return None


def _estado_foro(tipo_estado, nombre):
    return Estado.objects.filter(tipo_estado=tipo_estado, nombre=nombre).first()


def _solicitar_inicio_sesion(request):
    messages.info(request, "Inicia sesión para participar en el foro.")
    return redirect_to_login(
        reverse("mod_foro:publicaciones"),
        login_url=reverse("login_usuario"),
    )
