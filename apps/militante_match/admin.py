from django.contrib import admin

from .models import EleitorMilitanteMatch


@admin.register(EleitorMilitanteMatch)
class EleitorMilitanteMatchAdmin(admin.ModelAdmin):
    list_display = (
        "id", "eleitor", "militante", "score",
        "dt_nascimento_match", "status", "source", "created_at",
    )
    list_filter = ("status", "source", "dt_nascimento_match")
    search_fields = (
        "eleitor__nome", "militante__nome_completo",
        "militante__nm_pai", "militante__nm_mae",
    )
    raw_id_fields = ("eleitor", "militante", "confirmed_by")
