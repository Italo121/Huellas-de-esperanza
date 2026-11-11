import logging

from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import ValidationError
from django.db import DatabaseError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from mod_refugio.models import Estado, Usuario

from .forms import ComentarioForm, PublicacionForm
from .models import Comentario, Publicacion

logger = logging.getLogger(__name__)


def publicaciones(request):
    return _render_publicaciones(request)


def _render_publicaciones(request, publicacion_form=None):
    publicaciones = (
        Publicacion.objects.select_related("id_estado")
        .prefetch_related("comentarios__id_usuario", "comentarios__id_estado")
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
            publicacion.save()
        except DatabaseError:
            logger.exception("No se pudo guardar una publicación del foro")
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

    publicacion = get_object_or_404(Publicacion, pk=publicacion_id)
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
