from django.contrib import admin

from .models import CadernoEleitoral2026, CadernoEleitoral2026Import


@admin.register(CadernoEleitoral2026)
class CadernoEleitoral2026Admin(admin.ModelAdmin):
    list_display = ("numero", "nome", "nome_pai", "nome_mae", "mesa", "concelho", "posto", "data_nascimento", "descarga", "ativo")
    list_filter = ("ilha", "concelho", "posto", "mesa", "descarga", "ativo")
    search_fields = ("nome", "filiacao", "nome_pai", "nome_mae", "mesa")
    list_per_page = 50


@admin.register(CadernoEleitoral2026Import)
class CadernoEleitoral2026ImportAdmin(admin.ModelAdmin):
    list_display = ("nome_original", "status", "total_linhas", "processadas", "criadas", "atualizadas", "criado_em")
    list_filter = ("status",)
