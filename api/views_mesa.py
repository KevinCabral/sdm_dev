"""
ViewSets for Mesa, UserMesa and Eleitores resources with role-based access:

- Admin (superuser or 'admin' group)  → unrestricted
- Delegado ('delegado' group)         → only their assigned mesas + matching eleitores
- Anyone else                         → 403

Filtering on Eleitores is performed by `nr_mesa` string match against the
`Mesa.nr_mesa` of the user's UserMesa entries (Eleitor.nr_mesa is a CharField,
not a FK to Mesa).
"""
from django.contrib.auth.models import User
from django.db.models import Q
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import filters, mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.eleitores.models import Eleitores
from apps.eleitores.models import Votacao
from apps.mesa.models import Mesa, UserMesa

from .permissions import (
    IsAdmin,
    IsAdminOrDelegado,
    IsAdminOrReadOnlyDelegado,
    is_admin,
    is_delegado,
    user_mesa_ids,
    user_mesa_numbers,
)
from .serializers_mesa import (
    EleitorFlagsSerializer,
    EleitorListSerializer,
    EleitorMarkSerializer,
    EleitorSerializer,
    MesaSerializer,
    UserMesaBulkAssignSerializer,
    UserMesaSerializer,
    UserMiniSerializer,
    VotacaoRegisterSerializer,
    VotacaoSerializer,
    VotacaoUnregisterSerializer,
)


# ---------- Mesas ----------

class MesaViewSet(viewsets.ModelViewSet):
    """
    /api/mesas/

    - GET (list/detail): admin sees all, delegado sees only assigned mesas.
    - POST/PUT/PATCH/DELETE: admin only.
    """

    serializer_class = MesaSerializer
    permission_classes = [IsAdminOrReadOnlyDelegado]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["nr_mesa"]
    ordering_fields = ["nr_mesa", "createdAt", "updatedAt"]
    ordering = ["nr_mesa"]

    def get_queryset(self):
        qs = Mesa.objects.all()
        user = self.request.user
        if is_admin(user):
            return qs
        if is_delegado(user):
            return qs.filter(id__in=user_mesa_ids(user))
        return qs.none()

    def _object_belongs_to_user(self, obj, user):
        return obj.id in user_mesa_ids(user)

    @action(detail=True, methods=["get"], url_path="eleitores")
    def eleitores(self, request, pk=None):
        """List eleitores belonging to this mesa (respects user permissions)."""
        mesa = self.get_object()
        qs = Eleitores.objects.filter(nr_mesa=mesa.nr_mesa, falecido=False)

        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = EleitorListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        return Response(EleitorListSerializer(qs, many=True).data)


# ---------- UserMesa (admin-only assignments) ----------

class UserMesaViewSet(viewsets.ModelViewSet):
    """
    /api/user-mesas/  (admin only)

    Manage the UserMesa pivot — assign delegados to mesas.
    """

    serializer_class = UserMesaSerializer
    permission_classes = [IsAdmin]
    filter_backends = [filters.OrderingFilter]
    ordering = ["-createdAt"]

    def get_queryset(self):
        qs = UserMesa.objects.select_related("user", "mesa").all()
        user_id = self.request.query_params.get("user")
        mesa_id = self.request.query_params.get("mesa")
        if user_id:
            qs = qs.filter(user_id=user_id)
        if mesa_id:
            qs = qs.filter(mesa_id=mesa_id)
        return qs

    @action(detail=False, methods=["post"], url_path="bulk-assign")
    def bulk_assign(self, request):
        """
        Replace a user's mesa assignments with the provided list.

        Body: {"user": <user_id>, "mesas": [<mesa_id>, ...]}
        """
        serializer = UserMesaBulkAssignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        mesas = serializer.validated_data["mesas"]

        UserMesa.objects.filter(user=user).delete()
        UserMesa.objects.bulk_create(
            [UserMesa(user=user, mesa=mesa) for mesa in mesas]
        )
        created = UserMesa.objects.filter(user=user).select_related("user", "mesa")
        return Response(
            UserMesaSerializer(created, many=True).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=["get"], url_path=r"by-user/(?P<user_id>\d+)")
    def by_user(self, request, user_id=None):
        """List the mesas assigned to a given user."""
        qs = self.get_queryset().filter(user_id=user_id)
        return Response(self.get_serializer(qs, many=True).data)


# ---------- Eleitores ----------

class EleitorPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 500


class EleitorViewSet(viewsets.ModelViewSet):
    """
    /api/eleitores/

    - List/Detail: admin → all; delegado → only eleitores in their mesas.
    - Create/Update/Delete: admin only (delegado is read-only on collection).
    - Custom action `mark-descarga` (PATCH): allowed for delegado on owned eleitores
      so the field operator can flag who already voted.
    """

    permission_classes = [IsAdminOrDelegado]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["nome", "nominho", "filiacao", "=nr_eleitor", "nr_mesa"]
    ordering_fields = ["nome", "nr_eleitor", "datahora_atualizacao"]
    ordering = ["nome"]
    pagination_class = EleitorPagination

    @extend_schema(
        parameters=[
            OpenApiParameter("nr_mesa", str, description="Filtrar por nr_mesa exato"),
            OpenApiParameter("nr_eleitor", int, description="Filtrar por nr_eleitor exato"),
            OpenApiParameter("concelho", str, description="Filtrar por concelho exato"),
            OpenApiParameter("zona", str, description="Filtrar por zona exata"),
            OpenApiParameter("mpd", bool, description="true/false — eleitor MpD"),
            OpenApiParameter("indeciso", bool, description="true/false"),
            OpenApiParameter("ausente", bool, description="true/false"),
            OpenApiParameter("nao_vai_votar", bool, description="true/false"),
            OpenApiParameter("descarga", bool, description="true/false — já votou"),
        ],
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def get_serializer_class(self):
        if self.action == "list":
            return EleitorListSerializer
        if self.action == "mark_descarga":
            return EleitorMarkSerializer
        return EleitorSerializer

    def get_queryset(self):
        qs = Eleitores.objects.filter(falecido=False)
        user = self.request.user

        if is_admin(user):
            pass
        elif is_delegado(user):
            mesas = user_mesa_numbers(user)
            if not mesas:
                return qs.none()
            qs = qs.filter(nr_mesa__in=mesas)
        else:
            return qs.none()

        # Manual GET filters (no django-filter dependency)
        params = self.request.query_params
        for field in ("nr_mesa", "nr_eleitor", "concelho", "zona"):
            value = params.get(field)
            if value:
                qs = qs.filter(**{field: value})
        for boolean_field in ("mpd", "indeciso", "ausente", "nao_vai_votar", "descarga"):
            value = params.get(boolean_field)
            if value is not None and value != "":
                qs = qs.filter(**{boolean_field: value.lower() in ("1", "true", "yes")})
        return qs

    def _object_belongs_to_user(self, obj, user):
        return obj.nr_mesa in user_mesa_numbers(user)

    # Restrict write methods for delegados on the collection level
    def _check_write_allowed(self):
        if is_admin(self.request.user):
            return
        raise PermissionDenied("Apenas administradores podem modificar eleitores.")

    def create(self, request, *args, **kwargs):
        self._check_write_allowed()
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        self._check_write_allowed()
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        self._check_write_allowed()
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        """Soft-delete: set falecido=True instead of removing the row."""
        self._check_write_allowed()
        instance = self.get_object()
        instance.falecido = True
        instance.save(update_fields=["falecido", "datahora_atualizacao"])
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["patch"], url_path="mark-descarga")
    def mark_descarga(self, request, pk=None):
        """
        Mark/unmark an eleitor as voted (descarga).

        Allowed for admins, and for delegados on eleitores that belong to
        one of their assigned mesas (object-level check via permission class).
        """
        eleitor = self.get_object()  # triggers has_object_permission
        serializer = EleitorMarkSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        eleitor.descarga = serializer.validated_data["descarga"]
        eleitor.save(update_fields=["descarga", "datahora_atualizacao"])
        return Response(EleitorSerializer(eleitor).data)

    @action(detail=True, methods=["patch"], url_path="mark-flags")
    def mark_flags(self, request, pk=None):
        """
        Update one or more boolean flags on an eleitor.

        Accepts any subset of: `nao_vai_votar`, `ausente`, `indeciso`,
        `mpd`, `descarga`. Only the fields in the request body are updated.

        Permission scope mirrors `mark-descarga` (admins or delegados on
        their own mesas).
        """
        eleitor = self.get_object()
        serializer = EleitorFlagsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        update_fields = []
        for field, value in serializer.validated_data.items():
            setattr(eleitor, field, value)
            update_fields.append(field)
        update_fields.append("datahora_atualizacao")
        eleitor.save(update_fields=update_fields)
        return Response(EleitorSerializer(eleitor).data)

    @action(detail=True, methods=["patch"], url_path="mark-nao-vai-votar")
    def mark_nao_vai_votar(self, request, pk=None):
        """Convenience endpoint: set `nao_vai_votar` (default true)."""
        return self._toggle_flag(request, "nao_vai_votar")

    @action(detail=True, methods=["patch"], url_path="mark-ausente")
    def mark_ausente(self, request, pk=None):
        """Convenience endpoint: set `ausente` (default true)."""
        return self._toggle_flag(request, "ausente")

    @action(detail=True, methods=["patch"], url_path="mark-indeciso")
    def mark_indeciso(self, request, pk=None):
        """Convenience endpoint: set `indeciso` (default true)."""
        return self._toggle_flag(request, "indeciso")

    def _toggle_flag(self, request, field):
        eleitor = self.get_object()
        value = request.data.get(field, True)
        if not isinstance(value, bool):
            value = str(value).lower() in ("1", "true", "yes", "sim")
        setattr(eleitor, field, value)
        eleitor.save(update_fields=[field, "datahora_atualizacao"])
        return Response(EleitorSerializer(eleitor).data)

    @action(detail=False, methods=["get"], url_path=r"by-nr-eleitor/(?P<nr_eleitor>\d+)")
    def by_nr_eleitor(self, request, nr_eleitor=None):
        """
        Lookup a single eleitor by `nr_eleitor`.

        Respects the same access scope as the list endpoint:
        - admin: any eleitor
        - delegado: only if the eleitor's mesa is among their assignments
        Returns 404 if not found OR not visible to the requesting user.
        """
        eleitor = self.get_queryset().filter(nr_eleitor=nr_eleitor).first()
        if eleitor is None:
            return Response(
                {"detail": "Eleitor não encontrado."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(EleitorSerializer(eleitor).data)

    @action(detail=False, methods=["get"], url_path="my-mesas")
    def my_mesas(self, request):
        """Convenience endpoint: mesas the requesting user has access to."""
        user = request.user
        if is_admin(user):
            mesas = Mesa.objects.all()
        else:
            mesas = Mesa.objects.filter(id__in=user_mesa_ids(user))
        return Response(MesaSerializer(mesas.order_by("nr_mesa"), many=True).data)


# ---------- Votacao ----------

class VotacaoPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 500


class VotacaoViewSet(viewsets.ModelViewSet):
    """
    /api/votacoes/

    Votação records linked to eleitores via `nr_eleitor` (no FK on the legacy table).

    - List/Detail: admin → all; delegado → only votações in their mesas.
    - Create/Update/Delete: admin → any; delegado → only on their mesas.

    Custom actions
    --------------
    - POST   /api/votacoes/register-vote/         → register a vote for an eleitor
    - POST   /api/votacoes/unregister-vote/       → cancel/anular a vote
    - GET    /api/votacoes/by-eleitor/<nr>/       → fetch the vote(s) of an eleitor
    - GET    /api/votacoes/by-mesa/<nr_mesa>/     → list votes for a given mesa
    - GET    /api/votacoes/stats/                 → aggregated counts (per mesa, total)
    """

    permission_classes = [IsAdminOrDelegado]
    filter_backends = [filters.OrderingFilter]
    # NOTE: DRF SearchFilter is intentionally NOT used because `Votacao` has no FK
    # to `Eleitores`, so we cannot search by `nome` via the default backend.
    # Use the `search` / `nome` query params handled in `get_queryset` instead.
    ordering_fields = ["datetime", "nr_eleitor", "nr_mesa"]
    ordering = ["-datetime"]
    pagination_class = VotacaoPagination

    @extend_schema(
        parameters=[
            OpenApiParameter("search", str, description="Procura livre: nome/nominho do eleitor (ILIKE), nr_eleitor, BI, nr_mesa, assembleia ou motivo."),
            OpenApiParameter("nome", str, description="Procura por nome/nominho do eleitor (ILIKE)."),
            OpenApiParameter("anulado", bool, description="true → só anuladas; false → não anuladas (inclui NULL)"),
            OpenApiParameter("votou", bool, description="true → só onde votou=1; false → o resto"),
            OpenApiParameter("nr_mesa", str, description="Filtrar por nr_mesa exato"),
            OpenApiParameter("nr_eleitor", int, description="Filtrar por nr_eleitor exato"),
            OpenApiParameter("nr_bi_eleitor", str, description="Filtrar por BI exato"),
            OpenApiParameter("assembleia_voto_nr", str, description="Filtrar por assembleia exata"),
            OpenApiParameter("date_from", str, description="Data inicial (YYYY-MM-DD ou ISO 8601). Alias: datetime_from"),
            OpenApiParameter("date_to", str, description="Data final (YYYY-MM-DD ou ISO 8601). Alias: datetime_to"),
        ],
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def get_serializer_class(self):
        if self.action == "register_vote":
            return VotacaoRegisterSerializer
        if self.action == "unregister_vote":
            return VotacaoUnregisterSerializer
        return VotacaoSerializer

    def get_queryset(self):
        qs = Votacao.objects.all()
        user = self.request.user

        if is_admin(user):
            pass
        elif is_delegado(user):
            mesas = user_mesa_numbers(user)
            if not mesas:
                return qs.none()
            qs = qs.filter(nr_mesa__in=mesas)
        else:
            return qs.none()

        params = self.request.query_params
        for field in ("nr_mesa", "nr_eleitor", "assembleia_voto_nr", "nr_bi_eleitor"):
            value = params.get(field)
            if value:
                qs = qs.filter(**{field: value})
        anulado = params.get("anulado")
        if anulado is not None and anulado != "":
            truthy = anulado.lower() in ("1", "true", "yes", "sim")
            if truthy:
                qs = qs.filter(anulado=1)
            else:
                # "false" matches both 0 and NULL — votos não anulados
                qs = qs.exclude(anulado=1)
        votou = params.get("votou")
        if votou is not None and votou != "":
            truthy = votou.lower() in ("1", "true", "yes", "sim")
            qs = qs.filter(votou=1) if truthy else qs.exclude(votou=1)

        # Date range on `datetime` (ISO 8601 / YYYY-MM-DD accepted)
        date_from = params.get("datetime_from") or params.get("date_from")
        if date_from:
            qs = qs.filter(datetime__gte=date_from)
        date_to = params.get("datetime_to") or params.get("date_to")
        if date_to:
            qs = qs.filter(datetime__lte=date_to)

        # Free-text search: `?search=` (broad) and `?nome=` (nome/nominho only).
        # `Votacao` has no FK to `Eleitores`, so we resolve matching `nr_eleitor`
        # values from `Eleitores` first and then filter `Votacao` by them.
        nome = (params.get("nome") or "").strip()
        search = (params.get("search") or "").strip()
        term = nome or search
        if term:
            elei_q = Q(nome__icontains=term) | Q(nominho__icontains=term)
            nr_eleitores = list(
                Eleitores.objects.filter(elei_q)
                .exclude(nr_eleitor__isnull=True)
                .values_list("nr_eleitor", flat=True)[:5000]
            )
            if nome:
                # Restrict strictly to name matches.
                qs = qs.filter(nr_eleitor__in=nr_eleitores) if nr_eleitores else qs.none()
            else:
                # Broad search: name matches OR direct fields on votacao.
                broad = (
                    Q(nr_bi_eleitor__icontains=term)
                    | Q(nr_mesa__icontains=term)
                    | Q(assembleia_voto_nr__icontains=term)
                    | Q(motivo_n_votou__icontains=term)
                )
                if term.isdigit():
                    broad |= Q(nr_eleitor=int(term))
                if nr_eleitores:
                    broad |= Q(nr_eleitor__in=nr_eleitores)
                qs = qs.filter(broad)
        return qs

    def _object_belongs_to_user(self, obj, user):
        return obj.nr_mesa in user_mesa_numbers(user)

    def _check_mesa_allowed(self, nr_mesa):
        user = self.request.user
        if is_admin(user):
            return
        if nr_mesa not in user_mesa_numbers(user):
            raise PermissionDenied(
                "Sem permissão para registar votos nesta mesa."
            )

    @action(detail=False, methods=["post"], url_path="register-vote")
    def register_vote(self, request):
        """Register (or re-register) a vote for an eleitor.

        Also marks the eleitor as `descarga=True` so the changelist reflects it.
        Idempotent: if a non-anulado vote already exists for the same
        (nr_eleitor, nr_mesa), it is returned instead of duplicated.
        """
        serializer = VotacaoRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        eleitor = serializer.validated_data["eleitor"]
        self._check_mesa_allowed(eleitor.nr_mesa)

        existing = Votacao.objects.filter(
            nr_eleitor=eleitor.nr_eleitor,
            nr_mesa=eleitor.nr_mesa,
        ).exclude(anulado=1).first()

        if existing:
            return Response(
                VotacaoSerializer(existing).data,
                status=status.HTTP_200_OK,
            )

        from django.utils import timezone
        anulado = 1 if serializer.validated_data.get("anulado") else 0
        votou = 0 if anulado else 1
        votacao = Votacao.objects.create(
            assembleia_voto_nr=serializer.validated_data.get("assembleia_voto_nr") or None,
            nr_eleitor=eleitor.nr_eleitor,
            nr_bi_eleitor=serializer.validated_data.get("nr_bi_eleitor") or None,
            nr_mesa=eleitor.nr_mesa,
            votou=votou,
            anulado=anulado,
            motivo_n_votou=serializer.validated_data.get("motivo_n_votou") or None,
            datetime=timezone.now(),
        )

        if not anulado:
            eleitor.descarga = True
            eleitor.save(update_fields=["descarga", "datahora_atualizacao"])

        return Response(
            VotacaoSerializer(votacao).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=["post"], url_path="unregister-vote")
    def unregister_vote(self, request):
        """Anular a previously registered vote.

        Either `votacao_id` or `nr_eleitor` (+ optional `nr_mesa`) must be provided.
        Marks `anulado=1`, `votou=0`, sets `motivo_n_votou`, and resets the
        eleitor's `descarga` flag if no other valid vote exists.
        """
        serializer = VotacaoUnregisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        qs = self.get_queryset()
        if data.get("votacao_id"):
            votacao = qs.filter(pk=data["votacao_id"]).first()
        else:
            inner = qs.filter(nr_eleitor=data["nr_eleitor"])
            if data.get("nr_mesa"):
                inner = inner.filter(nr_mesa=data["nr_mesa"])
            votacao = inner.exclude(anulado=1).order_by("-datetime").first()

        if not votacao:
            return Response(
                {"detail": "Votação não encontrada."},
                status=status.HTTP_404_NOT_FOUND,
            )
        self._check_mesa_allowed(votacao.nr_mesa)

        votacao.anulado = 1
        votacao.votou = 0
        if data.get("motivo"):
            votacao.motivo_n_votou = data["motivo"]
        votacao.save(update_fields=["anulado", "votou", "motivo_n_votou"])

        # Reset eleitor.descarga if no more valid votes remain
        still_valid = Votacao.objects.filter(
            nr_eleitor=votacao.nr_eleitor, nr_mesa=votacao.nr_mesa
        ).exclude(anulado=1).exists()
        if not still_valid:
            eleitor = Eleitores.objects.filter(
                nr_eleitor=votacao.nr_eleitor, nr_mesa=votacao.nr_mesa
            ).first()
            if eleitor and eleitor.descarga:
                eleitor.descarga = False
                eleitor.save(update_fields=["descarga", "datahora_atualizacao"])

        return Response(VotacaoSerializer(votacao).data)

    @action(detail=False, methods=["get"], url_path=r"by-eleitor/(?P<nr_eleitor>\d+)")
    def by_eleitor(self, request, nr_eleitor=None):
        """Return all votação records for a given nr_eleitor (most recent first)."""
        qs = self.get_queryset().filter(nr_eleitor=nr_eleitor).order_by("-datetime")
        return Response(VotacaoSerializer(qs, many=True).data)

    @action(detail=False, methods=["get"], url_path=r"by-mesa/(?P<nr_mesa>[^/]+)")
    def by_mesa(self, request, nr_mesa=None):
        """Return all votação records for a given mesa."""
        self._check_mesa_allowed(nr_mesa)
        qs = self.get_queryset().filter(nr_mesa=nr_mesa).order_by("-datetime")
        page = self.paginate_queryset(qs)
        if page is not None:
            return self.get_paginated_response(VotacaoSerializer(page, many=True).data)
        return Response(VotacaoSerializer(qs, many=True).data)

    @action(detail=False, methods=["get"], url_path="stats")
    def stats(self, request):
        """Aggregated counts: votes/anuladas per mesa + grand totals (scoped by role)."""
        from django.db.models import Count, Q
        qs = self.get_queryset()
        per_mesa = list(
            qs.values("nr_mesa").annotate(
                total=Count("id"),
                votos_validos=Count("id", filter=Q(anulado=0) | Q(anulado__isnull=True)),
                anuladas=Count("id", filter=Q(anulado=1)),
            ).order_by("nr_mesa")
        )
        totals = qs.aggregate(
            total=Count("id"),
            votos_validos=Count("id", filter=Q(anulado=0) | Q(anulado__isnull=True)),
            anuladas=Count("id", filter=Q(anulado=1)),
        )
        return Response({"totals": totals, "per_mesa": per_mesa})
