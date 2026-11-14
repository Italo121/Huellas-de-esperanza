from .models import Personal
from mod_casa_temporal.models import CasaTemporal


def personal_context(request):
    session_user = request.session.get("refugio_usuario") or {}
    name_parts = (session_user.get("nombre") or "").split()
    nombre_usuario_navbar = (
        " ".join((name_parts[0], name_parts[-2]))
        if len(name_parts) > 2
        else " ".join(name_parts)
    )
    supabase_uid = session_user.get("id")
    roles_personal = []
    if supabase_uid:
        roles_personal = list(
            Personal.objects.filter(id_usuario__supabase_uid=supabase_uid)
            .values_list("rol", flat=True)
        )
    es_personal = bool(roles_personal)
    es_admin = "admin" in roles_personal
    tiene_hogar_temporal = bool(
        supabase_uid
        and CasaTemporal.objects.filter(
            id_usuario__supabase_uid=supabase_uid,
        ).exists()
    )
    return {
        "es_personal": es_personal,
        "es_admin": es_admin,
        "tiene_hogar_temporal": tiene_hogar_temporal,
        "nombre_usuario_navbar": nombre_usuario_navbar,
    }
