from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="militantes.index"),
    path("/notificacao-pedidos", views.notificacaoPedidos, name="militantes.notificacao"), 
    path("/create", views.create, name="militantes.create"), 
    path("/pedidos", views.pedidos, name="militantes.pedidos"), 
    path("/view/<int:id>/", views.view, name="militantes.view"), 
    path("/aprovar", views.aprovar, name="militantes.aprovar"), 
    path("/rejectar", views.rejectar, name="militantes.rejectar"), 
    path("/aprovados", views.aprovados, name="militantes.aprovados"), 
    path("/rejectados", views.rejectados, name="militantes.rejectados"), 
    path("/defaults", views.defaults, name="militantes.defaults"), 
    path("/get/<int:id>", views.get, name="militantes.get"), 
    path("/update/<int:id>/", views.update, name="militantes.update"), 
    path("/delete", views.delete, name="militantes.delete"), 
    path("/export/excel", views.exportExcel, name="militantes.exportExcel"),
    path("/getPais", views.getPais, name="militantes.getPais"), 
    path("/getIlhas", views.getIlhas, name="militantes.getIlhas"), 
    path("/getConcelho", views.getConcelho, name="militantes.getConcelho"), 
    path("/getFreguesia", views.getFreguesia, name="militantes.getFreguesia"), 
    path("/getZona", views.getZona, name="militantes.getZona"),
    path("/dashboard", views.dashboard, name="militantes.dashboard"),
    path("/distribuicao-genero", views.distribuicaoGenero, name="militantes.distribuicaoGenero"),
    path("/distribuicao-idade", views.distribuicaoIdade, name="militantes.distribuicaoIdade"),
    path("/distribuicao-zona", views.distribuicaoZona, name="militantes.distribuicaoZona"),
    path("/distribuicao-quotas", views.distribuicaoQuotas, name="militantes.distribuicaoQuotas"),
    path("/username", views.checkUsername, name="militantes.username"),
    path("/create-user", views.createUser, name="militantes.createUser")
    
    
    
]





