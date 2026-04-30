from django.urls import path

from . import views

urlpatterns = [
   path("", views.users, name="users.index"), 
   path("/bloquear", views.bloquear, name="users.bloquear"), 
   path("/ativar", views.ativar, name="users.ativar"), 
   path("/create-ajax", views.create_ajax, name="users.create_ajax"),
   path("/<int:user_id>/update-ajax", views.update_ajax, name="users.update_ajax"),
   path("/<int:user_id>/delete-ajax", views.delete_ajax, name="users.delete_ajax"),
   path('/profile/', views.updateProfile, name='users.profile'),
   path('/profile/change-password', views.change_my_password, name='users.change_my_password'),
   path('/gerar-password/<int:id>',views.generantePassword,name='users.generantePassword'),
   path('/change_password/<int:user_id>/', views.change_password, name='change_password'),
   
]




