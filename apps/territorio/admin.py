from django.contrib import admin

from .models import Circulo, Concelho, Zona


@admin.register(Circulo)
class CirculoAdmin(admin.ModelAdmin):
    list_display = ("nome", "codigo", "ativo", "meta")
    search_fields = ("nome", "codigo")
    list_filter = ("ativo",)


@admin.register(Concelho)
class ConcelhoAdmin(admin.ModelAdmin):
    list_display = ("nome", "codigo", "circulo", "ativo", "meta")
    search_fields = ("nome", "codigo")
    list_filter = ("ativo", "circulo")


@admin.register(Zona)
class ZonaAdmin(admin.ModelAdmin):
    list_display = ("nome", "codigo", "concelho", "ativo", "meta")
    search_fields = ("nome", "codigo")
    list_filter = ("ativo", "concelho__circulo", "concelho")
