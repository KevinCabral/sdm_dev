from django.urls import path

from . import views

urlpatterns = [
   path("", views.users, name="users.index"), 
   path("/bloquear", views.bloquear, name="users.bloquear"), 
   path("/ativar", views.ativar, name="users.ativar"), 
   path('/profile/', views.updateProfile, name='users.profile'),
   path('/gerar-password/<int:id>',views.generantePassword,name='users.generantePassword'),
   path('/change_password/<int:user_id>/', views.change_password, name='change_password'),
   
]




