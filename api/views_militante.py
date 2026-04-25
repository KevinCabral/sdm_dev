"""
Mobile API endpoints for Militantes.

Public:
- POST /api/militantes/register/        Self-registration (status → 'P').

Authenticated militante (linked via User.militante_id):
- GET    /api/militantes/me/            Read own profile.
- PATCH  /api/militantes/me/            Update own profile.
- DELETE /api/militantes/me/            Delete own account (soft).

Admin only:
- GET    /api/militantes/               List (filter by estado: P/A/R/D).
- GET    /api/militantes/{id}/          Detail.
- POST   /api/militantes/{id}/approve/  Approve → create User + email creds.
- POST   /api/militantes/{id}/reject/   Reject with motivo.
"""
import logging
import random
import re
import string

from django.contrib.auth.models import Group, User
from django.db import transaction

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.militantes.models import Militantes
from apps.users.models import SendUsernamePassword

from .permissions import is_admin
from .serializers_militante import (
    MilitanteAdminSerializer,
    MilitanteApproveSerializer,
    MilitantePublicRegisterSerializer,
    MilitanteRejectSerializer,
    MilitanteSelfSerializer,
)

logger = logging.getLogger(__name__)


# ---------- helpers ----------

def _random_password(length=12):
    alphabet = string.ascii_letters + string.digits
    return "".join(random.choice(alphabet) for _ in range(length))


def _suggest_username(militante):
    """Build a unique username from email / id."""
    base = ""
    if militante.email_pessoal:
        base = militante.email_pessoal.split("@", 1)[0]
    base = re.sub(r"[^A-Za-z0-9_.-]", "", base or "") or f"militante_{militante.pk}"
    base = base[:30]

    candidate = base
    suffix = 1
    while User.objects.filter(username=candidate).exists():
        suffix += 1
        candidate = f"{base[:28]}_{suffix}"
    return candidate


def _militante_for_user(user):
    """Return the Militantes row linked to the authenticated user, or None."""
    mid = getattr(user, "militante_id", None)
    if not mid:
        return None
    return Militantes.objects.filter(pk=mid).first()


# ---------- Public self-registration ----------

class MilitanteRegisterView(APIView):
    """POST /api/militantes/register/ — anonymous self-registration."""

    permission_classes = (AllowAny,)
    parser_classes = (MultiPartParser, FormParser, JSONParser)
    serializer_class = MilitantePublicRegisterSerializer

    @extend_schema(
        request=MilitantePublicRegisterSerializer,
        responses={201: MilitanteSelfSerializer},
        tags=["Militantes"],
    )
    def post(self, request):
        serializer = MilitantePublicRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        militante = serializer.save()
        return Response(
            {
                "detail": "Pedido de registo recebido. Aguarda aprovação.",
                "militante": MilitanteSelfSerializer(militante).data,
            },
            status=status.HTTP_201_CREATED,
        )


# ---------- Authenticated militante self-service ----------

class MilitanteMeView(APIView):
    """GET / PATCH / DELETE /api/militantes/me/ — own profile."""

    permission_classes = (IsAuthenticated,)
    parser_classes = (MultiPartParser, FormParser, JSONParser)
    serializer_class = MilitanteSelfSerializer

    def _get_object(self, request):
        militante = _militante_for_user(request.user)
        if not militante:
            raise NotFound("Nenhum militante associado a este utilizador.")
        if militante.estado_militante == "D":
            raise PermissionDenied("Conta de militante removida.")
        return militante

    @extend_schema(responses={200: MilitanteSelfSerializer}, tags=["Militantes"])
    def get(self, request):
        return Response(MilitanteSelfSerializer(self._get_object(request)).data)

    @extend_schema(
        request=MilitanteSelfSerializer,
        responses={200: MilitanteSelfSerializer},
        tags=["Militantes"],
    )
    def patch(self, request):
        militante = self._get_object(request)
        serializer = MilitanteSelfSerializer(
            militante, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @extend_schema(
        responses={204: None},
        tags=["Militantes"],
        description="Soft-delete: marca o militante como 'D' e desactiva o utilizador.",
    )
    def delete(self, request):
        militante = self._get_object(request)
        with transaction.atomic():
            militante.estado_militante = "D"
            militante.save(update_fields=["estado_militante"])
            user = request.user
            user.is_active = False
            user.save(update_fields=["is_active"])
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------- Admin endpoints ----------

class MilitanteAdminViewSet(viewsets.ReadOnlyModelViewSet):
    """
    /api/militantes/ (admin)

    - GET list/detail with optional ?estado=P|A|R|D filter.
    - POST {id}/approve/ → creates a User, links via militante_id, emails creds.
    - POST {id}/reject/  → marks 'R' with motivo.
    """

    serializer_class = MilitanteAdminSerializer
    permission_classes = (IsAuthenticated,)
    queryset = Militantes.objects.all().order_by("nome_completo")

    def _check_admin(self, request):
        if not is_admin(request.user):
            raise PermissionDenied("Apenas administradores.")

    @extend_schema(
        parameters=[
            OpenApiParameter(
                "estado", str, description="Filtrar por estado_militante (P/A/R/D)"
            ),
            OpenApiParameter("q", str, description="Pesquisa em nome/alcunha"),
        ],
        tags=["Militantes"],
    )
    def list(self, request, *args, **kwargs):
        self._check_admin(request)
        qs = self.get_queryset()
        estado = request.query_params.get("estado")
        if estado:
            qs = qs.filter(estado_militante=estado.upper())
        q = request.query_params.get("q")
        if q:
            from django.db.models import Q
            qs = qs.filter(Q(nome_completo__icontains=q) | Q(alcunha__icontains=q))

        page = self.paginate_queryset(qs)
        if page is not None:
            return self.get_paginated_response(self.get_serializer(page, many=True).data)
        return Response(self.get_serializer(qs, many=True).data)

    def retrieve(self, request, *args, **kwargs):
        self._check_admin(request)
        return super().retrieve(request, *args, **kwargs)

    @extend_schema(
        request=MilitanteApproveSerializer,
        tags=["Militantes"],
    )
    @action(detail=True, methods=["post"], url_path="approve")
    def approve(self, request, pk=None):
        self._check_admin(request)
        militante = self.get_object()

        if militante.estado_militante == "A":
            return Response(
                {"detail": "Militante já aprovado.",
                 "user_exists": User.objects.filter(militante_id=militante.pk).exists()},
                status=status.HTTP_200_OK,
            )

        serializer = MilitanteApproveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        email = (militante.email_pessoal or "").strip()
        if not email:
            return Response(
                {"detail": "Militante não tem email_pessoal definido."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Re-use an existing user already linked to this militante (idempotent).
        existing_user = User.objects.filter(militante_id=militante.pk).first()
        password = None
        with transaction.atomic():
            if existing_user:
                user = existing_user
                user.is_active = True
                user.save(update_fields=["is_active"])
            else:
                username = (data.get("username") or "").strip() or _suggest_username(militante)
                if User.objects.filter(username=username).exists():
                    return Response(
                        {"detail": f"Username '{username}' já existe."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                password = _random_password()
                user = User.objects.create_user(
                    username=username, email=email, password=password,
                )
                user.militante_id = militante.pk
                user.save(update_fields=["militante_id"])

            group_name = (data.get("group") or "militante").strip().lower()
            group, _ = Group.objects.get_or_create(name=group_name)
            user.groups.add(group)

            militante.estado_militante = "A"
            militante.save(update_fields=["estado_militante"])

        # Send credentials email only if we created a new user with a fresh password.
        emailed = False
        if password and data.get("send_email", True):
            try:
                mailer = SendUsernamePassword(
                    email=user.email,
                    username=user.username,
                    password=password,
                    request=request,
                )
                emailed = bool(mailer.send())
            except Exception:
                logger.exception("Approve: failed to send credentials email")

        return Response({
            "detail": "Militante aprovado.",
            "user_id": user.id,
            "username": user.username,
            "group": group_name,
            "email_sent": emailed,
            # NEVER return the password in production for an existing user — only on
            # first approval to allow the admin/mobile UI to display/copy it.
            "password": password,
        })

    @extend_schema(request=MilitanteRejectSerializer, tags=["Militantes"])
    @action(detail=True, methods=["post"], url_path="reject")
    def reject(self, request, pk=None):
        self._check_admin(request)
        militante = self.get_object()
        serializer = MilitanteRejectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        militante.estado_militante = "R"
        militante.motivo_rejeicao = serializer.validated_data["motivo"]
        militante.save(update_fields=["estado_militante", "motivo_rejeicao"])
        return Response({"detail": "Militante rejeitado."})
