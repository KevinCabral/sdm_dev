"""
Quotas mobile API.

Militante (auth, linked via User.militante_id):
- GET    /api/quotas/valores/       List available ValorPagamento options.
- GET    /api/quotas/me/            List own payments. Filters:
                                    ?data_inicio=YYYY-MM-DD&data_fim=YYYY-MM-DD
                                    &ano=YYYY&mes=MM&valor_id=
- POST   /api/quotas/me/            Create own payment (multipart with anexo_id).
- GET    /api/quotas/me/{id}/       Detail of own payment.
- GET    /api/quotas/me/stats/      Stats for the militant (total, count, by year, ...).

Admin:
- GET    /api/quotas/               List all payments with filters.
- GET    /api/quotas/{id}/          Detail.
- GET    /api/quotas/stats/         Global stats.
"""
import logging
from datetime import date

from django.db.models import Count, Max, Min, Sum
from django.db.models.functions import ExtractMonth, ExtractYear

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.militantes.models import Militantes
from apps.quotas.models import PagamentoQuotas, SendComprovativo, ValorPagamento

from .permissions import is_admin
from .serializers_quotas import (
    PagamentoQuotasSerializer,
    ValorPagamentoSerializer,
)

logger = logging.getLogger(__name__)


# ---------- helpers ----------

def _militante_for_user(user):
    mid = getattr(user, "militante_id", None)
    if not mid:
        return None
    return Militantes.objects.filter(pk=mid).first()


def _apply_filters(qs, params):
    """Apply common date / valor filters from query params to a payments qs."""
    data_inicio = params.get("data_inicio")
    data_fim = params.get("data_fim")
    ano = params.get("ano")
    mes = params.get("mes")
    valor_id = params.get("valor_id")

    if data_inicio and data_fim:
        qs = qs.filter(data_pagamento__range=(data_inicio, data_fim))
    elif data_inicio:
        qs = qs.filter(data_pagamento__gte=data_inicio)
    elif data_fim:
        qs = qs.filter(data_pagamento__lte=data_fim)
    if ano:
        try:
            qs = qs.filter(data_pagamento__year=int(ano))
        except (TypeError, ValueError):
            pass
    if mes:
        try:
            qs = qs.filter(data_pagamento__month=int(mes))
        except (TypeError, ValueError):
            pass
    if valor_id:
        qs = qs.filter(valor_id=valor_id)
    return qs


def _build_stats(qs):
    """Aggregate stats used by both the militant and admin endpoints."""
    today = date.today()
    agg = qs.aggregate(
        total_pago=Sum("valor__valor"),
        nr_pagamentos=Count("id"),
        primeiro=Min("data_pagamento"),
        ultimo=Max("data_pagamento"),
    )
    ano_corrente = qs.filter(data_pagamento__year=today.year).aggregate(
        total=Sum("valor__valor"), nr=Count("id"),
    )
    por_ano = list(
        qs.exclude(data_pagamento__isnull=True)
        .annotate(ano=ExtractYear("data_pagamento"))
        .values("ano")
        .annotate(total=Sum("valor__valor"), nr=Count("id"))
        .order_by("-ano")
    )
    por_mes_ano_corrente = list(
        qs.filter(data_pagamento__year=today.year)
        .annotate(mes=ExtractMonth("data_pagamento"))
        .values("mes")
        .annotate(total=Sum("valor__valor"), nr=Count("id"))
        .order_by("mes")
    )
    return {
        "total_pago": agg["total_pago"] or 0,
        "nr_pagamentos": agg["nr_pagamentos"] or 0,
        "primeiro_pagamento": agg["primeiro"],
        "ultimo_pagamento": agg["ultimo"],
        "ano_corrente": {
            "ano": today.year,
            "total": ano_corrente["total"] or 0,
            "nr": ano_corrente["nr"] or 0,
        },
        "por_ano": por_ano,
        "por_mes_ano_corrente": por_mes_ano_corrente,
    }


# ---------- ValorPagamento (read-only catalog) ----------

class ValorPagamentoViewSet(viewsets.ReadOnlyModelViewSet):
    """/api/quotas/valores/ — list payment value options."""

    serializer_class = ValorPagamentoSerializer
    permission_classes = (IsAuthenticated,)
    queryset = ValorPagamento.objects.all().order_by("valor")
    pagination_class = None  # tiny catalog; no need to paginate


# ---------- Militante self-service ----------

class MeQuotasView(APIView):
    """GET (list) / POST (create) /api/quotas/me/ — own payments."""

    permission_classes = (IsAuthenticated,)
    parser_classes = (MultiPartParser, FormParser, JSONParser)
    serializer_class = PagamentoQuotasSerializer

    def _militante(self, request):
        m = _militante_for_user(request.user)
        if not m:
            raise NotFound("Nenhum militante associado a este utilizador.")
        if m.estado_militante == "D":
            raise PermissionDenied("Conta de militante removida.")
        return m

    @extend_schema(
        parameters=[
            OpenApiParameter("data_inicio", str, description="YYYY-MM-DD"),
            OpenApiParameter("data_fim", str, description="YYYY-MM-DD"),
            OpenApiParameter("ano", int, description="Filtrar por ano"),
            OpenApiParameter("mes", int, description="Filtrar por mês (1-12)"),
            OpenApiParameter("valor_id", int, description="Filtrar por ValorPagamento"),
        ],
        responses={200: PagamentoQuotasSerializer(many=True)},
        tags=["Quotas"],
    )
    def get(self, request):
        militante = self._militante(request)
        qs = (
            PagamentoQuotas.objects
            .filter(militante=militante)
            .select_related("valor", "militante")
            .order_by("-data_pagamento", "-id")
        )
        qs = _apply_filters(qs, request.query_params)
        return Response(PagamentoQuotasSerializer(qs, many=True).data)

    @extend_schema(
        request=PagamentoQuotasSerializer,
        responses={201: PagamentoQuotasSerializer},
        tags=["Quotas"],
    )
    def post(self, request):
        militante = self._militante(request)
        serializer = PagamentoQuotasSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        pagamento = serializer.save(militante=militante)

        # Best-effort comprovativo email — never fail the request because of SMTP.
        try:
            if militante.email_pessoal and pagamento.anexo_id:
                mailer = SendComprovativo(
                    request=request,
                    email=militante.email_pessoal,
                    nome=militante.nome_completo,
                    text=(
                        "O seu pagamento foi confirmado, no valor: "
                        f"{pagamento.valor.valor if pagamento.valor else ''}."
                    ),
                    anexo=pagamento.anexo_id.path,
                )
                mailer.send()
        except Exception:
            logger.exception("Quotas: falha ao enviar comprovativo")

        return Response(
            PagamentoQuotasSerializer(pagamento).data,
            status=status.HTTP_201_CREATED,
        )


class MeQuotaDetailView(APIView):
    """GET /api/quotas/me/{id}/ — detail of own payment."""

    permission_classes = (IsAuthenticated,)
    serializer_class = PagamentoQuotasSerializer

    @extend_schema(responses={200: PagamentoQuotasSerializer}, tags=["Quotas"])
    def get(self, request, pk):
        militante = _militante_for_user(request.user)
        if not militante:
            raise NotFound("Nenhum militante associado a este utilizador.")
        pagamento = (
            PagamentoQuotas.objects
            .select_related("valor", "militante")
            .filter(pk=pk, militante=militante)
            .first()
        )
        if not pagamento:
            raise NotFound("Pagamento não encontrado.")
        return Response(PagamentoQuotasSerializer(pagamento).data)


class MeQuotasStatsView(APIView):
    """GET /api/quotas/me/stats/ — stats for the militant's own payments."""

    permission_classes = (IsAuthenticated,)

    @extend_schema(tags=["Quotas"])
    def get(self, request):
        militante = _militante_for_user(request.user)
        if not militante:
            raise NotFound("Nenhum militante associado a este utilizador.")
        qs = PagamentoQuotas.objects.filter(militante=militante)
        return Response(_build_stats(qs))


# ---------- Admin ----------

class AdminQuotasViewSet(viewsets.ReadOnlyModelViewSet):
    """/api/quotas/ — admin list/detail + global stats."""

    serializer_class = PagamentoQuotasSerializer
    permission_classes = (IsAuthenticated,)
    queryset = (
        PagamentoQuotas.objects
        .select_related("valor", "militante")
        .order_by("-data_pagamento", "-id")
    )

    def _check_admin(self, request):
        if not is_admin(request.user):
            raise PermissionDenied("Apenas administradores.")

    @extend_schema(
        parameters=[
            OpenApiParameter("nome", str, description="Pesquisa em nome do militante"),
            OpenApiParameter("militante_id", int),
            OpenApiParameter("data_inicio", str, description="YYYY-MM-DD"),
            OpenApiParameter("data_fim", str, description="YYYY-MM-DD"),
            OpenApiParameter("ano", int),
            OpenApiParameter("mes", int),
            OpenApiParameter("valor_id", int),
        ],
        tags=["Quotas"],
    )
    def list(self, request, *args, **kwargs):
        self._check_admin(request)
        qs = self.get_queryset()
        nome = request.query_params.get("nome")
        militante_id = request.query_params.get("militante_id")
        if nome:
            qs = qs.filter(militante__nome_completo__icontains=nome)
        if militante_id:
            qs = qs.filter(militante_id=militante_id)
        qs = _apply_filters(qs, request.query_params)

        page = self.paginate_queryset(qs)
        if page is not None:
            return self.get_paginated_response(self.get_serializer(page, many=True).data)
        return Response(self.get_serializer(qs, many=True).data)

    def retrieve(self, request, *args, **kwargs):
        self._check_admin(request)
        return super().retrieve(request, *args, **kwargs)

    @extend_schema(tags=["Quotas"])
    @action(detail=False, methods=["get"], url_path="stats")
    def stats(self, request):
        self._check_admin(request)
        qs = _apply_filters(self.get_queryset(), request.query_params)
        return Response(_build_stats(qs))
