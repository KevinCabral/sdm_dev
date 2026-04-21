from django.urls import path

from . import views

urlpatterns = [
    path("/index", views.index, name="mesa.index"), 
    path("/createOrUpdate", views.createOrUpdate, name="mesa.create_update"),
    path("/mesa/view", views.get, name="mesa.view"),
    path("/remover", views.remover, name="mesa.remover"),
    path("/export/excel", views.exportExcel, name="mesa.exportExcel"),

    path("/mesa/index", views.indexMesa, name="mesa.index_mesa"), 
    path("/mesa/createOrUpdate", views.createOrUpdateMesa, name="mesa.create_update_mesa"),
    path("/mesa/mesa/view", views.getMesa, name="mesa.view_mesa"),
    path("/mesa/remover", views.removerMesa, name="mesa.remover_mesa"),
    path("/mesa/export/excel", views.exportExcelMesa, name="mesa.exportExcel_mesa"),
    
]





