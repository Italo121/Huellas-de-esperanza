from .models import Personal
from mod_casa_temporal.models import CasaTemporal


def personal_context(request):
    session_user = request.session.get("refugio_usuario") or {}
    supabase_uid = session_user.get("id")
    es_personal = bool(
        supabase_uid
        and Personal.objects.filter(
            id_usuario__supabase_uid=supabase_uid,
        ).exists()
    )
    tiene_hogar_temporal = bool(
        supabase_uid
        and CasaTemporal.objects.filter(
            id_usuario__supabase_uid=supabase_uid,
        ).exists()
    )
    return {
        "es_personal": es_personal,
        "tiene_hogar_temporal": tiene_hogar_temporal,
    }
