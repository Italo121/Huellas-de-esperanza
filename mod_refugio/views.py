from django.shortcuts import render

from .models import Animal


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
    return render(
        request,
        "index.html",
        {
            "animales": animales,
            "especies": especies,
        },
    )