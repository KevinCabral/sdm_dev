"""core URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import include, path
from rest_framework.authtoken.views import obtain_auth_token # <-- NEW
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic.base import RedirectView

from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView,
)

from apps.militantes import views
from apps.users.password_reset import (
    PasswordResetCodeConfirmView,
    PasswordResetCompleteView,
    PasswordResetRequestView,
)

urlpatterns = [
    path('', views.dashboard),
    # path('home', include('home.urls')),
    path('api/', include('api.urls')),
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
    path('users', include('apps.users.urls')),
    path('militantes', include('apps.militantes.urls')),
    path('admin/login/', RedirectView.as_view(url='/accounts/login/', permanent=False)),
    path("admin/", admin.site.urls),
    path("carta-convite", include('apps.carta_convite.urls')),
    path("eleitores", include('apps.eleitores.urls')),
    path("quotas", include('apps.quotas.urls')),
    path("mesas", include('apps.mesa.urls')),

    # Code-based password reset (overrides admin_datta's link-based flow).
    # Registered BEFORE admin_datta so URL resolution picks our views,
    # and AGAIN after admin_datta so `reverse()` (which prefers the last
    # occurrence of a name) also returns our URLs.
    path('accounts/password-reset/', PasswordResetRequestView.as_view(), name='password_reset'),
    path('accounts/password-reset-confirm/', PasswordResetCodeConfirmView.as_view(), name='password_reset_confirm'),
    path('accounts/password-reset-complete/', PasswordResetCompleteView.as_view(), name='password_reset_complete'),

    path("", include('admin_datta.urls')),
    path('', include('django_dyn_dt.urls')),  # <-- NEW: Dynamic_DT Routing

    # Re-register so reverse() prefers our patterns over admin_datta's.
    path('accounts/password-reset/', PasswordResetRequestView.as_view(), name='password_reset'),
    path('accounts/password-reset-confirm/', PasswordResetCodeConfirmView.as_view(), name='password_reset_confirm'),
    path('accounts/password-reset-complete/', PasswordResetCompleteView.as_view(), name='password_reset_complete'),
]  + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# Lazy-load on routing is needed
# During the first build, API is not yet generated
# try:
urlpatterns.append( path("api/"      , include("api.urls"))    )
urlpatterns.append( path("login/jwt/", view=obtain_auth_token) )
# except:
    # pass


