"""API endpoints exposing the eleitor ↔ militante matched dataset.

Two read-only resources, designed primarily for the mobile app used by
``gestor_militantes``:

* ``GET /api/eleitores-militantes/`` — paginated list of eleitores that
  have been confirmed as a militante (via :class:`EleitorMilitanteMatch`
  or the legacy ``eleitores.militante_id_id`` FK), enriched with the
  militante contact numbers and lat/lng so the field team can call /
  navigate to them.

* ``GET /api/eleitores-militantes/voting-pace/`` — turnout intelligence:
  given an 8-hour election window, returns expected vs actual cumulative
  votes per hour and a boolean ``is_slow`` flag the mobile app uses to
  decide when to start phoning militantes.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta

from django.db.models import Q
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import filters, mixins, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from apps.eleitores.models import Eleitores, Votacao
from apps.militante_match.models import EleitorMilitanteMatch

from .permissions import (
    IsAdminOrGestorMilitantes,
    is_admin,
    is_gestor_militantes,
)
from .serializers_militante_match import (
    EleitorMilitanteSerializer,
    VotingPaceResponseSerializer,
)


DEFAULT_DURATION_HOURS = 8
DEFAULT_SLOW_THRESHOLD = 0.85  # actual < 85% of expected → "slow"


class EleitorMilitantePagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 500


def _militante_eleitor_queryset():
    """Return the Eleitores that have been linked to a militante.

    Source of truth: a *confirmed* row in ``EleitorMilitanteMatch``. We
    also accept the legacy ``militante_id_id`` FK to remain compatible
    with rows imported before the matcher existed.
    """
    confirmed_ids = EleitorMilitanteMatch.objects.filter(
        status=EleitorMilitanteMatch.STATUS_CONFIRMED,
    ).values_list("eleitor_id", flat=True)

    return (
        Eleitores.objects
        .select_related("militante_id")
        .filter(falecido=False)
        .filter(Q(id__in=confirmed_ids) | Q(militante_id__isnull=False))
    )


class EleitorMilitanteViewSet(mixins.ListModelMixin,
                              mixins.RetrieveModelMixin,
                              viewsets.GenericViewSet):
    """Read-only resource consumed by the ``gestor_militantes`` mobile app."""

    serializer_class = EleitorMilitanteSerializer
    permission_classes = [IsAdminOrGestorMilitantes]
    pagination_class = EleitorMilitantePagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = [
        "nome", "nominho",
        "militante_id__nome_completo",
        "militante_id__alcunha",
        "=nr_eleitor",
    ]
    ordering_fields = ["nome", "nr_mesa", "nr_eleitor"]
    ordering = ["nome"]

    @extend_schema(
        parameters=[
            OpenApiParameter("nr_mesa", str, description="Filtrar por nr_mesa exato"),
            OpenApiParameter("concelho", str, description="Filtrar por concelho"),
            OpenApiParameter("zona", str, description="Filtrar por zona"),
            OpenApiParameter("ja_votou", bool, description="true → só quem já votou; false → pendentes"),
        ],
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        qs = _militante_eleitor_queryset()
        params = self.request.query_params
        for field in ("nr_mesa", "concelho", "zona"):
            value = params.get(field)
            if value:
                qs = qs.filter(**{field: value})
        ja_votou = params.get("ja_votou")
        if ja_votou is not None and ja_votou != "":
            truthy = ja_votou.lower() in ("1", "true", "yes", "sim")
            qs = qs.filter(descarga=truthy)
        return qs

    # ------------------------------------------------------------------
    # Voting pace intelligence
    # ------------------------------------------------------------------
    @extend_schema(
        parameters=[
            OpenApiParameter("nr_mesa", str, description="Filtrar pelo nr_mesa (opcional)"),
            OpenApiParameter("start_at", str, description="Início da eleição (ISO 8601). Default: hoje 08:00 local."),
            OpenApiParameter("duration_hours", int, description=f"Duração total em horas (default {DEFAULT_DURATION_HOURS})."),
            OpenApiParameter("threshold", float, description=f"Limite de 'lento' (default {DEFAULT_SLOW_THRESHOLD})."),
        ],
        responses={200: VotingPaceResponseSerializer},
    )
    @action(detail=False, methods=["get"], url_path="voting-pace")
    def voting_pace(self, request):
        """Compare expected vs actual militante turnout at this hour.

        Algorithm
        ---------
        1. Determine the election window ``[start_at, end_at]`` (default
           today 08:00 local → +8h).
        2. ``total_militantes`` = number of confirmed eleitor↔militante
           rows (optionally filtered by ``nr_mesa``).
        3. For each hour bucket inside the window, count the number of
           those militantes whose ``Votacao`` row has ``votou=1``,
           ``anulado != 1`` and ``datetime <= bucket_end``.
        4. Compute the expected linear cumulative vote at each bucket
           (``total * elapsed_fraction``) and flag a bucket / the whole
           election as ``is_slow`` when actual is below
           ``threshold * expected``.
        """
        nr_mesa = request.query_params.get("nr_mesa") or None
        try:
            duration_hours = int(request.query_params.get("duration_hours") or DEFAULT_DURATION_HOURS)
        except ValueError:
            duration_hours = DEFAULT_DURATION_HOURS
        try:
            threshold = float(request.query_params.get("threshold") or DEFAULT_SLOW_THRESHOLD)
        except ValueError:
            threshold = DEFAULT_SLOW_THRESHOLD

        start_at = self._parse_start(request.query_params.get("start_at"))
        end_at = start_at + timedelta(hours=duration_hours)

        militante_qs = _militante_eleitor_queryset()
        if nr_mesa:
            militante_qs = militante_qs.filter(nr_mesa=nr_mesa)
        nr_eleitores = list(
            militante_qs.exclude(nr_eleitor__isnull=True)
            .values_list("nr_eleitor", flat=True)
        )
        total = len(nr_eleitores)

        # Pull all votação rows for these eleitores within the window in a
        # single query, then bucket in Python — much cheaper than N hourly
        # queries.
        votos_qs = (
            Votacao.objects
            .filter(
                nr_eleitor__in=nr_eleitores,
                votou=1,
                datetime__gte=start_at,
                datetime__lt=end_at,
            )
            .exclude(anulado=1)
            .values_list("datetime", flat=True)
        )
        # Distinct by nr_eleitor to avoid double-counting if a row was
        # re-registered. The DB can have multiple Votacao rows per eleitor;
        # we want first-vote-only.
        first_vote_by_eleitor: dict[int, datetime] = {}
        for nre, dt in (
            Votacao.objects
            .filter(
                nr_eleitor__in=nr_eleitores,
                votou=1,
                datetime__gte=start_at,
                datetime__lt=end_at,
            )
            .exclude(anulado=1)
            .values_list("nr_eleitor", "datetime")
        ):
            existing = first_vote_by_eleitor.get(nre)
            if existing is None or dt < existing:
                first_vote_by_eleitor[nre] = dt

        votes_dt = sorted(first_vote_by_eleitor.values())
        voted = len(votes_dt)
        pending = max(0, total - voted)
        percent_voted = (voted / total * 100.0) if total else 0.0

        now = timezone.now()
        elapsed = max(timedelta(0), min(now, end_at) - start_at)
        elapsed_hours = elapsed.total_seconds() / 3600.0
        expected_now = int(round(total * (elapsed_hours / duration_hours))) if duration_hours else 0
        delta_now = voted - expected_now
        is_slow = (
            total > 0
            and elapsed_hours > 0
            and voted < expected_now * threshold
        )

        # Build hourly buckets.
        buckets = []
        for i in range(duration_hours):
            bucket_start = start_at + timedelta(hours=i)
            bucket_end = bucket_start + timedelta(hours=1)
            actual_cum = sum(1 for dt in votes_dt if dt < bucket_end)
            expected_cum = int(round(total * ((i + 1) / duration_hours)))
            buckets.append({
                "hour": i,
                "label": f"{bucket_start.strftime('%H:%M')}–{bucket_end.strftime('%H:%M')}",
                "expected_cumulative": expected_cum,
                "actual_cumulative": actual_cum,
                "delta": actual_cum - expected_cum,
                "is_slow": (
                    bucket_end <= now
                    and total > 0
                    and actual_cum < expected_cum * threshold
                ),
            })

        payload = {
            "total_militantes": total,
            "voted": voted,
            "pending": pending,
            "percent_voted": round(percent_voted, 2),
            "expected_now": expected_now,
            "delta_now": delta_now,
            "is_slow": is_slow,
            "start_at": start_at,
            "end_at": end_at,
            "duration_hours": float(duration_hours),
            "elapsed_hours": round(elapsed_hours, 2),
            "threshold_pct": threshold,
            "by_hour": buckets,
            "nr_mesa": nr_mesa,
        }
        return Response(VotingPaceResponseSerializer(payload).data)

    @staticmethod
    def _parse_start(raw):
        if raw:
            dt = timezone.datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if timezone.is_naive(dt):
                dt = timezone.make_aware(dt, timezone.get_current_timezone())
            return dt
        # Default: today at 08:00 local time.
        tz = timezone.get_current_timezone()
        today_local = timezone.localtime(timezone.now(), tz).date()
        return timezone.make_aware(datetime.combine(today_local, time(8, 0)), tz)
