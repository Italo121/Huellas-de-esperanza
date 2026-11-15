import logging

from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.db import DatabaseError
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render, resolve_url
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from mod_refugio.models import Personal, Usuario

from .forms import DonacionForm, NecesidadForm
from .models import Donacion, Necesidad

logger = logging.getLogger(__name__)


def _usuario_de_sesion(request):
    session_user = request.session.get("refugio_usuario")
    if not session_user:
        return None, redirect_to_login(
            request.get_full_path(),
            login_url=resolve_url("login_usuario"),
        )

    supabase_uid = session_user.get("id")
    if not supabase_uid:
        return None, HttpResponseForbidden(
            "No pudimos verificar tu cuenta. Inicia sesión nuevamente."
        )

    try:
        usuario = Usuario.objects.get(supabase_uid=supabase_uid)
    except Usuario.DoesNotExist:
        return None, HttpResponseForbidden(
            "No encontramos los datos asociados a tu cuenta."
        )
    except DatabaseError:
        logger.exception("Unable to find the signed-in donation user")
        return None, HttpResponse(
            "No fue posible verificar tu cuenta. Inténtalo más tarde.",
            status=503,
        )
    return usuario, None


def _personal_de_sesion(request):
    usuario, error_response = _usuario_de_sesion(request)
    if error_response:
        return None, error_response

    try:
        es_personal = Personal.objects.filter(id_usuario=usuario).exists()
    except DatabaseError:
        logger.exception("Unable to verify staff access for user %s", usuario.pk)
        return None, HttpResponse(
            "No fue posible verificar los permisos del personal.",
            status=503,
        )
    if not es_personal:
        return None, HttpResponseForbidden(
            "Solo el personal del refugio puede gestionar las donaciones."
        )
    return usuario, None


@require_http_methods(["GET"])
def necesidades(request):
    try:
        lista_necesidades = list(
            Necesidad.objects.order_by("saciada", "-fecha", "-id_necesidad")
        )
    except DatabaseError:
        logger.exception("Unable to load shelter needs")
        return HttpResponse(
            "No fue posible cargar las necesidades del refugio.",
            status=503,
        )

    return render(
        request,
        "mod_donacion/necesidades.html",
        {"necesidades": lista_necesidades},
    )


@require_http_methods(["GET", "POST"])
def crear_necesidad(request):
    _, error_response = _personal_de_sesion(request)
    if error_response:
        return error_response

    form = NecesidadForm(
        data=request.POST if request.method == "POST" else None
    )
    if request.method == "POST" and form.is_valid():
        necesidad = form.save(commit=False)
        necesidad.saciada = False
        necesidad.fecha = timezone.localdate()
        try:
            necesidad.save()
        except DatabaseError:
            logger.exception("Unable to save a shelter need")
            form.add_error(
                None,
                "No pudimos guardar la necesidad. Inténtalo nuevamente.",
            )
        else:
            messages.success(request, "La necesidad se registró correctamente.")
            return redirect("mod_donacion:necesidades")

    return render(
        request,
        "mod_donacion/crear_necesidad.html",
        {"form": form},
    )


@require_http_methods(["GET"])
def gestion_donaciones(request):
    _, error_response = _personal_de_sesion(request)
    if error_response:
        return error_response

    try:
        donaciones_independientes = list(
            Donacion.objects.filter(id_necesidad__isnull=True)
            .select_related("id_usuario")
            .order_by("-fecha_donacion", "-id_donacion")
        )
        necesidades_registradas = list(
            Necesidad.objects.order_by("saciada", "-fecha", "-id_necesidad")
        )
        donaciones_vinculadas = (
            Donacion.objects.filter(id_necesidad__isnull=False)
            .select_related("id_usuario", "id_necesidad")
            .order_by("-fecha_donacion", "-id_donacion")
        )
        donaciones_por_necesidad = {}
        for donacion in donaciones_vinculadas:
            donaciones_por_necesidad.setdefault(
                donacion.id_necesidad_id, []
            ).append(donacion)

        for necesidad in necesidades_registradas:
            necesidad.donaciones_registradas = donaciones_por_necesidad.get(
                necesidad.pk, []
            )
    except DatabaseError:
        logger.exception("Unable to load donations for staff management")
        return HttpResponse(
            "No fue posible cargar las donaciones del refugio.",
            status=503,
        )

    return render(
        request,
        "mod_donacion/gestion_donaciones.html",
        {
            "donaciones_independientes": donaciones_independientes,
            "necesidades": necesidades_registradas,
        },
    )


@require_POST
def marcar_necesidad_saciada(request, necesidad_id):
    _, error_response = _personal_de_sesion(request)
    if error_response:
        return error_response

    try:
        necesidad = get_object_or_404(Necesidad, pk=necesidad_id)
        if necesidad.saciada:
            messages.info(request, "Esta necesidad ya estaba marcada como saciada.")
        else:
            necesidad.saciada = True
            necesidad.fecha_cambio = timezone.localdate()
            necesidad.save(update_fields=["saciada", "fecha_cambio"])
            messages.success(
                request,
                "La necesidad se marcó como saciada correctamente.",
            )
    except DatabaseError:
        logger.exception(
            "Unable to mark shelter need %s as satisfied",
            necesidad_id,
        )
        return HttpResponse(
            "No fue posible actualizar el estado de la necesidad.",
            status=503,
        )

    return redirect("mod_donacion:gestion_donaciones")


@require_http_methods(["GET", "POST"])
def crear_donacion(request):
    usuario, error_response = _usuario_de_sesion(request)
    if error_response:
        return error_response

    necesidad_id = (
        request.GET.get("necesidad")
        if request.method == "GET"
        else request.POST.get("id_necesidad")
    )
    necesidad_preseleccionada = None
    if necesidad_id:
        try:
            necesidad_preseleccionada = Necesidad.objects.filter(
                pk=necesidad_id,
                saciada=False,
            ).first()
        except (TypeError, ValueError):
            necesidad_preseleccionada = None
        except DatabaseError:
            logger.exception("Unable to load the selected shelter need")
            return HttpResponse(
                "No fue posible cargar la necesidad seleccionada.",
                status=503,
            )

    form = DonacionForm(
        data=request.POST if request.method == "POST" else None,
        initial=(
            {"id_necesidad": necesidad_id}
            if request.method == "GET"
            else None
        ),
        necesidad=necesidad_preseleccionada,
    )
    if request.method == "POST":
        try:
            es_valida = form.is_valid()
        except DatabaseError:
            logger.exception("Unable to validate a donation for user %s", usuario.pk)
            return HttpResponse(
                "No fue posible validar la necesidad seleccionada.",
                status=503,
            )
        if es_valida:
            donacion = form.save(commit=False)
            donacion.id_usuario = usuario
            donacion.fecha_donacion = timezone.localdate()
            try:
                donacion.save()
            except DatabaseError:
                logger.exception(
                    "Unable to save a donation for user %s", usuario.pk
                )
                form.add_error(
                    None,
                    "No pudimos registrar tu donación. Inténtalo nuevamente.",
                )
            else:
                messages.success(request, "Tu donación se registró correctamente.")
                return redirect("mod_donacion:necesidades")

    return render(
        request,
        "mod_donacion/crear_donacion.html",
        {"form": form},
    )
