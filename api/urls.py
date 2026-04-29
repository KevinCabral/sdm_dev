from django.urls import path

from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView, TokenVerifyView

from .views import (
    ChangePasswordView,
    LoginView,
    LogoutView,
    MeView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    UserRegistration,
)
from .views_mesa import EleitorViewSet, MesaViewSet, UserMesaViewSet, VotacaoViewSet
from .views_militante_match import EleitorMilitanteViewSet
from .views_militante import (
    MilitanteAdminViewSet,
    MilitanteMeView,
    MilitanteRegisterView,
)
from .views_quotas import (
    AdminQuotasViewSet,
    MeQuotaDetailView,
    MeQuotasStatsView,
    MeQuotasView,
    ValorPagamentoViewSet,
)

router = DefaultRouter()
router.register(r"mesas", MesaViewSet, basename="api-mesa")
router.register(r"user-mesas", UserMesaViewSet, basename="api-user-mesa")
router.register(r"eleitores", EleitorViewSet, basename="api-eleitor")
router.register(r"votacoes", VotacaoViewSet, basename="api-votacao")
router.register(r"eleitores-militantes", EleitorMilitanteViewSet, basename="api-eleitor-militante")
router.register(r"militantes", MilitanteAdminViewSet, basename="api-militante")
router.register(r"quotas/valores", ValorPagamentoViewSet, basename="api-quota-valor")
router.register(r"quotas", AdminQuotasViewSet, basename="api-quota")

urlpatterns = [
    # Auth (Bearer JWT)
    path("auth/login/", LoginView.as_view(), name="api-auth-login"),
    path("auth/logout/", LogoutView.as_view(), name="api-auth-logout"),
    path("auth/refresh/", TokenRefreshView.as_view(), name="api-auth-refresh"),
    path("auth/verify/", TokenVerifyView.as_view(), name="api-auth-verify"),
    path("auth/me/", MeView.as_view(), name="api-auth-me"),
    path("auth/register/", UserRegistration.as_view(), name="api-auth-register"),

    # Password management
    path(
        "auth/password/change/",
        ChangePasswordView.as_view(),
        name="api-auth-password-change",
    ),
    path(
        "auth/password/reset/",
        PasswordResetRequestView.as_view(),
        name="api-auth-password-reset",
    ),
    path(
        "auth/password/reset/confirm/",
        PasswordResetConfirmView.as_view(),
        name="api-auth-password-reset-confirm",
    ),

    # --- Backwards-compatible aliases (legacy URLs) ---
    path("login", LoginView.as_view()),
    path("registrar", UserRegistration.as_view()),
    path("alterar-password", ChangePasswordView.as_view()),
    path("recuperar-password", PasswordResetRequestView.as_view()),

    # --- Militantes (mobile) ---
    # These must be registered BEFORE the router so they take precedence over
    # the `/militantes/<pk>/` detail route exposed by MilitanteAdminViewSet.
    path("militantes/register/", MilitanteRegisterView.as_view(), name="api-militante-register"),
    path("militantes/me/", MilitanteMeView.as_view(), name="api-militante-me"),

    # --- Quotas (mobile) ---
    # Same trick: explicit /quotas/me/* paths must come before router urls so
    # they aren't shadowed by /quotas/<pk>/ from AdminQuotasViewSet.
    path("quotas/me/", MeQuotasView.as_view(), name="api-quotas-me"),
    path("quotas/me/stats/", MeQuotasStatsView.as_view(), name="api-quotas-me-stats"),
    path("quotas/me/<int:pk>/", MeQuotaDetailView.as_view(), name="api-quotas-me-detail"),
]

# REST resource endpoints (mesas, user-mesas, eleitores)
urlpatterns += router.urls
