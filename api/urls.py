from django.urls import re_path, include, path
from django.views.decorators.csrf import csrf_exempt
from .views import UserRegistration, ChangePasswordView, LoginView, RecoverPasswordView
from rest_framework import routers

# router = routers.DefaultRouter()
# router.register(r'users', UserViewSet)
# router.register(r'groups', GroupViewSet)

urlpatterns = [
	path('registrar', UserRegistration.as_view(), name='registrar'),
	path('alterar-password', ChangePasswordView.as_view(), name='alterar-password'),
    path('login', LoginView.as_view(), name='api-login'),
	path('recuperar-password', RecoverPasswordView.as_view(), name='recuperar-password'),
]
