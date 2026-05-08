from django.contrib import admin

from .models import PotencialVotante, PotencialVotanteImport


@admin.register(PotencialVotante)
class PotencialVotanteAdmin(admin.ModelAdmin):
    list_display = ('nome', 'localidade', 'telefone', 'assinatura', 'ativo', 'criado_em')
    list_filter = ('assinatura', 'ativo', 'localidade')
    search_fields = ('nome', 'telefone', 'localidade')


@admin.register(PotencialVotanteImport)
class PotencialVotanteImportAdmin(admin.ModelAdmin):
    list_display = ('nome_original', 'status', 'total_linhas', 'processadas', 'criadas', 'criado_em')
    list_filter = ('status',)
